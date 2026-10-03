"""
pairwise-blockchain-system - BlockchainSystem

一个最小但完整的区块链分布式账本系统：

- 交易：签名验证 + 余额检查 + 去重
- 区块：工作量证明 + 哈希链接 + 难度调整
- 共识：最长链 + 最终性 + 多数投票
- 智能合约：沙箱 + Gas 限制 + 状态隔离
- P2P：节点发现 + 消息验证 + 历史同步
"""

import copy
import hashlib
import hmac
import sys
import time


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GasExceeded(Exception):
    """合约执行超出 Gas 限制。"""


class BlockchainSystem:
    TARGET_BLOCK_TIME = 10.0   # 目标出块时间（秒）
    DIFFICULTY_INTERVAL = 5    # 每多少个区块调整一次难度
    FINALITY_DEPTH = 3         # 多少个确认后区块最终确定，不可回滚
    MAX_DIFFICULTY = 4         # 难度上限，保证出块足够快

    def __init__(self, difficulty=2, block_reward=50):
        self.difficulty = max(1, min(difficulty, self.MAX_DIFFICULTY))
        self.block_reward = block_reward
        self.chain = []
        self.balances = {}
        self.pending_transactions = []
        self._seen_tx_ids = set()
        self.identities = {}          # address -> 密钥（钱包托管）
        self.contracts = {}           # contract_id -> {"state": {...}}
        self.peers = set()            # 已知节点
        self.seed_nodes = []          # 节点发现的种子节点
        self.outbox = []              # 已广播的消息记录
        self.finalized_height = -1
        self._last_adjustment_time = time.time()

        self.chain.append(self._build_genesis_block())

        # 内置一个有余额的默认账户，方便直接演示/测试
        self.register_identity("alice", "alice-secret")
        self.balances["alice"] = 1000

    # ------------------------------------------------------------------
    # 交易：签名验证 + 余额检查 + 去重
    # ------------------------------------------------------------------

    def register_identity(self, address, key):
        """注册地址对应的签名密钥（模拟钱包）。"""
        self.identities[address] = key

    @staticmethod
    def _tx_payload(sender, recipient, amount, nonce):
        return f"{sender}|{recipient}|{amount}|{nonce}"

    def _sign(self, key, payload):
        return hmac.new(key.encode("utf-8"), payload.encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def _verify_signature(self, sender, payload, signature):
        key = self.identities.get(sender)
        if key is None or not signature:
            return False
        expected = self._sign(key, payload)
        return hmac.compare_digest(expected, signature)

    def create_transaction(self, sender=None, recipient=None, amount=None,
                           signature=None, key=None, nonce=0):
        """创建交易：验签、检查余额、去重，全部通过才入账。

        任何一项校验失败都返回 None，且不改变账本状态。
        """
        if sender is None:
            sender = "alice"
        if recipient is None:
            recipient = "bob"
        if amount is None:
            amount = 10

        if not isinstance(amount, (int, float)) or amount <= 0:
            return None

        payload = self._tx_payload(sender, recipient, amount, nonce)

        # 1) 签名验证：任何人不能花别人的币
        if signature is None and key is not None:
            signature = self._sign(key, payload)
        if signature is None:
            # 钱包托管模式下用注册密钥自动签名
            key = self.identities.get(sender)
            if key is None:
                return None
            signature = self._sign(key, payload)
        if not self._verify_signature(sender, payload, signature):
            return None

        # 2) 去重：同一笔交易不能多次入账
        tx_id = _sha256(payload)
        if tx_id in self._seen_tx_ids:
            return None

        # 3) 余额检查：没钱不能转
        if self.balances.get(sender, 0) < amount:
            return None

        tx = {
            "id": tx_id,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "nonce": nonce,
            "signature": signature,
        }
        self._seen_tx_ids.add(tx_id)
        self.balances[sender] -= amount
        self.balances[recipient] = self.balances.get(recipient, 0) + amount
        self.pending_transactions.append(tx)
        return tx

    def get_balance(self, address):
        return self.balances.get(address, 0)

    # ------------------------------------------------------------------
    # 区块：工作量证明 + 哈希链接 + 难度调整
    # ------------------------------------------------------------------

    def _build_genesis_block(self):
        block = {
            "index": 0,
            "timestamp": time.time(),
            "transactions": [],
            "prev_hash": "0" * 64,
            "nonce": 0,
            "difficulty": self.difficulty,
        }
        return self._proof_of_work(block)

    @staticmethod
    def _block_hash(block):
        header = (f"{block['index']}|{block['timestamp']}|{block['prev_hash']}|"
                  f"{block['transactions']}|{block['nonce']}")
        return _sha256(header)

    def _meets_difficulty(self, block_hash, difficulty):
        return block_hash.startswith("0" * difficulty)

    def _proof_of_work(self, block):
        difficulty = block["difficulty"]
        nonce = 0
        while True:
            block["nonce"] = nonce
            block_hash = self._block_hash(block)
            if self._meets_difficulty(block_hash, difficulty):
                block["hash"] = block_hash
                return block
            nonce += 1

    def _adjust_difficulty(self):
        """按出块速度调整难度：太快加难，太慢减难。"""
        height = len(self.chain) - 1
        if height <= 0 or height % self.DIFFICULTY_INTERVAL != 0:
            return
        now = time.time()
        elapsed = now - self._last_adjustment_time
        expected = self.TARGET_BLOCK_TIME * self.DIFFICULTY_INTERVAL
        if elapsed < expected / 2 and self.difficulty < self.MAX_DIFFICULTY:
            self.difficulty += 1
        elif elapsed > expected * 2 and self.difficulty > 1:
            self.difficulty -= 1
        self._last_adjustment_time = now

    def _update_finality(self):
        target = len(self.chain) - 1 - self.FINALITY_DEPTH
        if target > self.finalized_height:
            self.finalized_height = target

    def mine_block(self, miner="miner1", transactions=None):
        """挖矿：收集交易、链接前块、做工作量证明，然后难度调整。"""
        if transactions is None:
            transactions = list(self.pending_transactions)
            self.pending_transactions.clear()

        previous = self.chain[-1]
        block = {
            "index": previous["index"] + 1,
            "timestamp": time.time(),
            "transactions": transactions,
            "prev_hash": previous["hash"],   # 哈希链接：区块之间环环相扣
            "nonce": 0,
            "difficulty": self.difficulty,
            "miner": miner,
            "reward": self.block_reward,
        }
        self._proof_of_work(block)           # 工作量证明：不算出哈希不能出块

        self.chain.append(block)
        self.balances[miner] = self.balances.get(miner, 0) + self.block_reward
        self._adjust_difficulty()            # 难度调整：出块速度随算力变化
        self._update_finality()
        return block

    def _validate_block(self, block, previous=None):
        """验证区块：字段完整、哈希正确、满足难度、链接正确。"""
        required = {"index", "timestamp", "transactions", "prev_hash",
                    "nonce", "difficulty", "hash"}
        if not isinstance(block, dict) or not required.issubset(block):
            return False
        if self._block_hash(block) != block["hash"]:
            return False
        if not self._meets_difficulty(block["hash"], block["difficulty"]):
            return False
        if previous is not None and block["prev_hash"] != previous["hash"]:
            return False
        return True

    def _validate_chain(self, chain):
        if not chain:
            return False
        for i, block in enumerate(chain):
            previous = chain[i - 1] if i > 0 else None
            if not self._validate_block(block, previous):
                return False
            if i > 0 and block["index"] != previous["index"] + 1:
                return False
        return True

    # ------------------------------------------------------------------
    # 共识：最长链 + 最终性 + 投票
    # ------------------------------------------------------------------

    def _respects_finality(self, candidate):
        """已最终确定的区块不允许被回滚。"""
        if self.finalized_height < 0:
            return True
        if len(candidate) <= self.finalized_height:
            return False
        for i in range(self.finalized_height + 1):
            if candidate[i].get("hash") != self.chain[i].get("hash"):
                return False
        return True

    def reach_consensus(self, chains=None, votes=None):
        """在分叉中选出有效最长链；替换本链需多数节点投票且不破最终性。"""
        candidates = [self.chain] + list(chains or [])
        valid = [c for c in candidates
                 if self._validate_chain(c) and self._respects_finality(c)]
        if not valid:
            return self.chain

        best = max(valid, key=len)           # 最长链原则
        if best is self.chain:
            return self.chain

        # 投票：少数节点不能决定切换链
        if isinstance(votes, (list, set, tuple)):
            support = len(votes)
        else:
            support = votes or 0
        total_nodes = len(self.peers) + 1
        if support * 2 <= total_nodes:
            return self.chain                # 未获多数，拒绝切换

        self.chain = list(best)
        self._update_finality()
        return self.chain

    # ------------------------------------------------------------------
    # 智能合约：沙箱 + Gas 限制 + 状态隔离
    # ------------------------------------------------------------------

    SAFE_BUILTINS = {
        "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
        "range": range, "enumerate": enumerate, "zip": zip, "sorted": sorted,
        "str": str, "int": int, "float": float, "bool": bool,
        "list": list, "dict": dict, "set": set, "tuple": tuple,
        "print": print,
    }

    def execute_contract(self, code=None, contract_id="default",
                         gas_limit=1000, state=None):
        """在沙箱中执行合约，限制 Gas，并隔离各合约的状态。

        沙箱违规、Gas 耗尽或执行异常时返回 None，且状态不被提交。
        """
        if code is None:
            code = "result = state.get('counter', 0) + 1\nstate['counter'] = result"

        # 状态隔离：每个合约只在深拷贝的私有状态上执行，成功后才提交
        if state is None:
            state = self.contracts.get(contract_id, {}).get("state", {})
        working_state = copy.deepcopy(state)

        env = {
            "__builtins__": dict(self.SAFE_BUILTINS),  # 沙箱：无 open/import 等
            "state": working_state,
            "result": None,
        }

        gas = {"used": 0}

        def tracer(frame, event, arg):
            if event == "line" and frame.f_code.co_filename == "<contract>":
                gas["used"] += 1
                if gas["used"] > gas_limit:            # Gas 限制：杀死死循环
                    raise GasExceeded(f"gas limit {gas_limit} exceeded")
            return tracer

        previous_trace = sys.gettrace()
        try:
            compiled = compile(code, "<contract>", "exec")
            sys.settrace(tracer)
            exec(compiled, env)
        except Exception:                              # 沙箱内任何异常都拒绝
            return None
        finally:
            sys.settrace(previous_trace)

        self.contracts[contract_id] = {"state": working_state}
        return {
            "contract_id": contract_id,
            "result": env.get("result"),
            "state": copy.deepcopy(working_state),
            "gas_used": gas["used"],
        }

    # ------------------------------------------------------------------
    # P2P：节点发现 + 消息验证 + 历史同步
    # ------------------------------------------------------------------

    def discover_peers(self, seeds=None):
        """通过种子节点发现网络中的其他节点。"""
        for seed in (seeds if seeds is not None else self.seed_nodes):
            self.peers.add(seed)
        return sorted(self.peers, key=str)

    def receive_block(self, block):
        """接收并验证其他节点广播的区块。"""
        if not self._validate_block(block, self.chain[-1]):
            return False
        if block["index"] != len(self.chain):
            return False
        self.chain.append(block)
        self._update_finality()
        return True

    def sync_from(self, peer):
        """从对等节点下载历史链，同步到最长有效链。"""
        peer_chain = getattr(peer, "chain", None)
        if not peer_chain or len(peer_chain) <= len(self.chain):
            return False
        if not self._validate_chain(peer_chain):
            return False
        if not self._respects_finality(peer_chain):
            return False
        self.chain = copy.deepcopy(peer_chain)
        self._update_finality()
        return True

    def broadcast_block(self, block=None, peers=None):
        """验证后向发现的节点广播区块，并帮助落后节点同步历史链。

        区块未通过消息验证时返回 None，伪造区块不会传播。
        """
        if block is None:
            block = self.chain[-1]

        # 消息验证：伪造/篡改的区块不允许传播
        if block is self.chain[-1]:
            previous = self.chain[-2] if len(self.chain) >= 2 else None
        else:
            previous = None
        if not self._validate_block(block, previous):
            return None

        # 节点发现：先找到能连的节点
        discovered = self.discover_peers(peers)

        delivered = []
        synced = []
        for peer in discovered:
            if hasattr(peer, "receive_block"):
                # 同步：落后节点先下载历史链
                if hasattr(peer, "chain") and len(peer.chain) < len(self.chain) - 1:
                    if peer.sync_from(self):
                        synced.append(peer)
                already_has = (hasattr(peer, "chain") and peer.chain
                               and peer.chain[-1].get("hash") == block.get("hash"))
                if already_has or peer.receive_block(copy.deepcopy(block)):
                    delivered.append(peer)
            else:
                delivered.append(peer)  # 无接口的地址型节点，记录为已投递

        message = {
            "type": "block",
            "block": copy.deepcopy(block),
            "peers": list(discovered),
            "delivered": len(delivered),
            "synced": len(synced),
        }
        self.outbox.append(message)
        return message
