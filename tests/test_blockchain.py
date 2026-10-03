import pytest
from blockchain.system import BlockchainSystem


class TestBlockchainSystem:

    def test_create_transaction(self):
        """创建交易不做签名验证，任何人都能花别人的币"""
        obj = BlockchainSystem()
        result = obj.create_transaction()
        self.assertIsNotNone(result)

    def test_mine_block(self):
        """区块不做工作量证明，随便就能出块"""
        obj = BlockchainSystem()
        result = obj.mine_block()
        self.assertIsNotNone(result)

    def test_reach_consensus(self):
        """共识不做最长链，分叉了不选最长"""
        obj = BlockchainSystem()
        result = obj.reach_consensus()
        self.assertIsNotNone(result)

    def test_execute_contract(self):
        """智能合约不做沙箱，能访问外部资源"""
        obj = BlockchainSystem()
        result = obj.execute_contract()
        self.assertIsNotNone(result)

    def test_broadcast_block(self):
        """P2P不做节点发现，连不上其他节点"""
        obj = BlockchainSystem()
        result = obj.broadcast_block()
        self.assertIsNotNone(result)

