"""
pairwise-blockchain-system - BlockchainSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class BlockchainSystem:
    def __init__(self):
        self.state = {}

    def create_transaction(self, *args, **kwargs):
        """BUG: 创建交易不做签名验证，任何人都能花别人的币"""
        return None

    def mine_block(self, *args, **kwargs):
        """BUG: 区块不做工作量证明，随便就能出块"""
        return None

    def reach_consensus(self, *args, **kwargs):
        """BUG: 共识不做最长链，分叉了不选最长"""
        return None

    def execute_contract(self, *args, **kwargs):
        """BUG: 智能合约不做沙箱，能访问外部资源"""
        return None

    def broadcast_block(self, *args, **kwargs):
        """BUG: P2P不做节点发现，连不上其他节点"""
        return None

