# -*- coding: utf-8 -*-
from typing import Iterable, Union
from itertools import zip_longest
from collections import namedtuple

from coincurve import PrivateKey, PublicKey
from eth_utils import to_checksum_address, encode_hex, keccak, remove_0x_prefix


def public_key_to_address(public_key: Union[PublicKey, bytes]) -> str:
    """ Converts a public key to an Ethereum address. """
    if isinstance(public_key, PublicKey):
        public_key = public_key.format(compressed=False)
    assert isinstance(public_key, bytes)
    return encode_hex(keccak(public_key[1:])[-20:])


def private_key_to_address(private_key: str) -> str:
    """ Converts a private key to an Ethereum address. """
    return to_checksum_address(
        public_key_to_address(PrivateKey.from_hex(remove_0x_prefix(private_key)).public_key)
    )


def _hash_pair(first: bytes, second: bytes) -> bytes:
    """ Computes the hash of the items in lexicographic order """
    if first is None:
        return second

    if second is None:
        return first

    if first > second:
        return keccak(second + first)
    else:
        return keccak(first + second)


EMPTY_MERKLE_ROOT = b'\x00' * 32

MerkleTree = namedtuple('MerkleTree', ['layers'])


def compute_merkle_tree(items: Iterable[bytes]) -> MerkleTree:
    """ Calculates the merkle root for a given list of items """

    if not all(isinstance(l, bytes) and len(l) == 32 for l in items):
        raise ValueError('Not all items are hashes')

    leaves = sorted(items)
    if len(leaves) == 0:
        return MerkleTree(layers=[[EMPTY_MERKLE_ROOT]])

    if not len(leaves) == len(set(leaves)):
        raise ValueError('The items must not cointain duplicate items')

    tree = [leaves]
    layer = leaves
    while len(layer) > 1:
        # [a, b, c, d, e] -> [(a, b), (c, d), (e, None)]
        iterator = iter(layer)
        paired_items = zip_longest(iterator, iterator)

        layer = [_hash_pair(a, b) for a, b in paired_items]
        tree.append(layer)

    return MerkleTree(layers=tree)


def get_merkle_root(merkle_tree: MerkleTree) -> bytes:
    """ Returns the root element of the merkle tree. """
    assert merkle_tree.layers, 'the merkle tree layers are empty'
    assert merkle_tree.layers[-1], 'the root layer is empty'

    return merkle_tree.layers[-1][0]
