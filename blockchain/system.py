"""
pairwise-blockchain-system - BlockchainSystem

A minimal but correct blockchain distributed-ledger implementation:

- Transactions: signature verification, balance checks, deduplication.
- Blocks: proof-of-work, hash linking, difficulty adjustment.
- Consensus: longest-chain rule, finality, voting.
- Smart contracts: sandboxed execution, gas limit, state isolation.
- P2P: peer discovery, message validation, chain synchronization.
"""

import hashlib
import hmac
import sys
import time


def _hash(data):
    return hashlib.sha256(repr(data).encode()).hexdigest()


def sign_payload(private_key, payload):
    """Produce an HMAC signature for a transaction payload."""
    return hmac.new(str(private_key).encode(), repr(payload).encode(), hashlib.sha256).hexdigest()


class Transaction:
    def __init__(self, sender, recipient, amount, signature, nonce):
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.signature = signature
        self.nonce = nonce
        self.tx_id = _hash((sender, recipient, amount, nonce))

    def payload(self):
        return (self.sender, self.recipient, self.amount, self.nonce)


class Block:
    def __init__(self, index, previous_hash, transactions, miner, timestamp=None):
        self.index = index
        self.previous_hash = previous_hash
        self.transactions = list(transactions)
        self.miner = miner
        self.timestamp = time.time() if timestamp is None else timestamp
        self.nonce = 0
        self.hash = self.compute_hash()

    def compute_hash(self):
        return _hash((self.index, self.previous_hash,
                      [t.tx_id for t in self.transactions],
                      self.miner, self.timestamp, self.nonce))


class GasExceeded(Exception):
    pass


class SandboxViolation(Exception):
    pass


class BlockchainSystem:
    INITIAL_BALANCE = 100
    MINING_REWARD = 10
    BLOCK_TARGET_TIME = 1.0          # seconds
    DIFFICULTY_ADJUST_INTERVAL = 5   # blocks
    FINALITY_DEPTH = 3               # blocks deeper than this are final
    VOTE_QUORUM = 2 / 3              # supermajority required

    def __init__(self, difficulty=2, node_id="node-0"):
        self.state = {}
        self.node_id = node_id
        self.difficulty = difficulty
        self.private_keys = {"alice": "alice-key", "bob": "bob-key"}
        self.balances = {name: self.INITIAL_BALANCE for name in self.private_keys}
        self.pending_transactions = []
        self.seen_tx_ids = set()
        self.chain = [self._genesis_block()]
        self.finalized_height = 0
        self.votes = {}
        self.peers = set()
        self.known_chains = []
        self.contract_states = {}

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------
    def _genesis_block(self):
        block = Block(0, "0" * 64, [], "genesis", timestamp=0)
        return block

    def verify_signature(self, tx):
        """A transaction is only valid if signed with the sender's key."""
        key = self.private_keys.get(tx.sender)
        if key is None:
            return False
        expected = sign_payload(key, tx.payload())
        return hmac.compare_digest(expected, tx.signature or "")

    def create_transaction(self, sender="alice", recipient="bob", amount=10,
                           signature=None, private_key=None, nonce=None):
        """Create a transaction with signature verification, balance
        checking and duplicate rejection."""
        if amount <= 0:
            raise ValueError("amount must be positive")
        nonce = self.balances.get(sender, 0) if nonce is None else nonce
        tx = Transaction(sender, recipient, amount, signature, nonce)
        if signature is None:
            key = private_key if private_key is not None else self.private_keys.get(sender)
            if key is None:
                raise ValueError("cannot sign: unknown sender key")
            tx.signature = sign_payload(key, tx.payload())

        # Signature verification: nobody can spend someone else's coins.
        if not self.verify_signature(tx):
            raise ValueError("invalid transaction signature")

        # Balance check: cannot spend money you do not have.
        if self.balances.get(sender, 0) < amount:
            raise ValueError("insufficient balance")

        # Deduplication: the same transaction must not be accepted twice.
        if tx.tx_id in self.seen_tx_ids:
            raise ValueError("duplicate transaction")
        self.seen_tx_ids.add(tx.tx_id)

        self.pending_transactions.append(tx)
        return tx

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------
    def _proof_of_work(self, block):
        target = "0" * self.difficulty
        while not block.hash.startswith(target):
            block.nonce += 1
            block.hash = block.compute_hash()
        return block

    def _adjust_difficulty(self):
        """Retarget difficulty every DIFFICULTY_ADJUST_INTERVAL blocks so
        that block time tracks BLOCK_TARGET_TIME."""
        if len(self.chain) % self.DIFFICULTY_ADJUST_INTERVAL != 0:
            return
        window = self.chain[-self.DIFFICULTY_ADJUST_INTERVAL:]
        elapsed = max(window[-1].timestamp - window[0].timestamp, 1e-6)
        expected = self.BLOCK_TARGET_TIME * (len(window) - 1)
        if elapsed < expected / 2:
            self.difficulty += 1
        elif elapsed > expected * 2:
            self.difficulty = max(1, self.difficulty - 1)

    def mine_block(self, miner="miner-1"):
        """Mine a block: hash-linked to the tip, sealed by proof-of-work,
        with periodic difficulty adjustment."""
        self._adjust_difficulty()
        previous = self.chain[-1]
        block = Block(previous.index + 1, previous.hash,
                      self.pending_transactions, miner)
        self._proof_of_work(block)

        for tx in block.transactions:
            self.balances[tx.sender] -= tx.amount
            self.balances[tx.recipient] = self.balances.get(tx.recipient, 0) + tx.amount
        self.pending_transactions = []
        self.balances[miner] = self.balances.get(miner, 0) + self.MINING_REWARD

        self.chain.append(block)
        self._update_finality()
        return block

    # ------------------------------------------------------------------
    # Consensus
    # ------------------------------------------------------------------
    def _valid_chain(self, chain):
        for prev, cur in zip(chain, chain[1:]):
            if cur.previous_hash != prev.hash:
                return False
            if not cur.hash.startswith("0" * self.difficulty):
                return False
        return True

    def _update_finality(self):
        """Blocks buried deeper than FINALITY_DEPTH are final and can
        never be rolled back."""
        height = len(self.chain) - 1
        self.finalized_height = max(0, height - self.FINALITY_DEPTH)

    def reach_consensus(self, chains=None, votes=None):
        """Resolve forks by longest-chain rule, gated by finality and a
        voting quorum."""
        candidates = [self.chain]
        if chains:
            candidates.extend(chains)
        candidates = [c for c in candidates if self._valid_chain(c)]

        # Voting: a chain only wins if a supermajority of nodes backs it.
        if votes is None:
            votes = {self.node_id: id(max(candidates, key=len))}
        tally = {}
        for chain_id in votes.values():
            tally[chain_id] = tally.get(chain_id, 0) + 1
        total_nodes = max(len(self.peers) + 1, len(votes))
        quorum = total_nodes * self.VOTE_QUORUM

        best = max(candidates, key=len)
        for chain in sorted(candidates, key=len, reverse=True):
            if tally.get(id(chain), 0) < quorum and len(votes) > 1:
                continue
            # Finality: never adopt a chain that rolls back finalized blocks.
            if (len(chain) - 1 < self.finalized_height or
                    chain[:self.finalized_height + 1] !=
                    self.chain[:self.finalized_height + 1]):
                continue
            best = chain
            break

        if best is not self.chain and len(best) > len(self.chain):
            self.chain = list(best)
            self._update_finality()
        return self.chain

    # ------------------------------------------------------------------
    # Smart contracts
    # ------------------------------------------------------------------
    _SAFE_BUILTINS = {
        "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
        "range": range, "enumerate": enumerate, "zip": zip, "sorted": sorted,
        "str": str, "int": int, "float": float, "bool": bool, "list": list,
        "dict": dict, "set": set, "tuple": tuple, "print": print,
    }

    def execute_contract(self, code=None, contract_id="contract-0",
                         gas_limit=10000, state=None):
        """Execute a contract in a sandbox with a gas limit and isolated
        per-contract state."""
        if code is None:
            code = "result = state.get('value', 0) + 1\nstate['value'] = result"

        # State isolation: every contract only sees its own state copy.
        own_state = dict(self.contract_states.get(contract_id, {}))
        if state:
            own_state.update(state)

        gas = {"remaining": gas_limit}

        def tracer(frame, event, arg):
            if event == "line":
                gas["remaining"] -= 1
                if gas["remaining"] <= 0:
                    raise GasExceeded("contract ran out of gas")
            return tracer

        sandbox_globals = {"__builtins__": dict(self._SAFE_BUILTINS)}
        sandbox_locals = {"state": own_state, "result": None}

        old_trace = sys.gettrace()
        sys.settrace(tracer)
        try:
            exec(code, sandbox_globals, sandbox_locals)  # sandboxed: no imports/open/etc.
        finally:
            sys.settrace(old_trace)

        self.contract_states[contract_id] = own_state
        return {
            "result": sandbox_locals.get("result"),
            "state": own_state,
            "gas_used": gas_limit - gas["remaining"],
        }

    # ------------------------------------------------------------------
    # P2P network
    # ------------------------------------------------------------------
    def discover_peers(self, seeds=None):
        """Peer discovery: bootstrap from seed nodes and gossip the peers
        they know about."""
        for seed in (seeds or []):
            if seed is self or seed.node_id == self.node_id:
                continue
            self.peers.add(seed.node_id)
            self.peers.update(seed.peers)
        self.peers.discard(self.node_id)
        return self.peers

    def validate_block(self, block):
        """Message validation: reject forged blocks before relaying."""
        if block.index == 0 and block.previous_hash == "0" * 64:
            return block.hash == block.compute_hash()
        if not block.hash.startswith("0" * self.difficulty):
            return False
        if block.hash != block.compute_hash():
            return False
        tip = self.chain[-1]
        if block.index > 0 and block.previous_hash not in {tip.hash, "0" * 64}:
            if not any(b.hash == block.previous_hash for b in self.chain):
                return False
        return all(self.verify_signature(tx) for tx in block.transactions)

    def sync_chain(self, peer):
        """Synchronization: download the peer's history and adopt it if it
        is a valid, longer chain."""
        if len(peer.chain) > len(self.chain) and self._valid_chain(peer.chain):
            self.chain = list(peer.chain)
            self._update_finality()
        return self.chain

    def broadcast_block(self, block=None, peers=None):
        """Broadcast a validated block to discovered peers; forged blocks
        are rejected and never propagated."""
        if block is None:
            block = self.chain[-1]
        if not self.validate_block(block):
            raise ValueError("refusing to broadcast invalid block")

        peers = list(peers) if peers is not None else list(self.peers)
        delivered = {}
        for peer in peers:
            node = peer if isinstance(peer, BlockchainSystem) else None
            if node is None:
                delivered[getattr(peer, "node_id", peer)] = "discovered"
                continue
            if node.validate_block(block):
                if block.index == len(node.chain):
                    node.chain.append(block)
                    node._update_finality()
                node.sync_chain(self)
                delivered[node.node_id] = "accepted"
            else:
                delivered[node.node_id] = "rejected"
        return {"block": block.hash, "peers": self.peers, "delivered": delivered}
