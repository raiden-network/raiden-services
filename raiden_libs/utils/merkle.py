from collections import namedtuple
from typing import Iterable, Tuple
from itertools import zip_longest
from eth_utils import keccak


EMPTY_MERKLE_ROOT = b'\x00' * 32

MerkleTree = namedtuple('MerkleTree', ['layers'])


def split_in_pairs(arg: Iterable) -> Iterable[Tuple]:
    """ Split given iterable in pairs [a, b, c, d, e] -> [(a, b), (c, d), (e, None)]"""
    # We are using zip_longest with one clever hack:
    # https://docs.python.org/3/library/itertools.html#itertools.zip_longest
    # We create an iterator out of the list and then pass the same iterator to
    # the function two times. Thus the function consumes a different element
    # from the iterator each time and produces the desired result.
    iterator = iter(arg)
    return zip_longest(iterator, iterator)


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
        paired_items = split_in_pairs(layer)

        layer = [_hash_pair(a, b) for a, b in paired_items]
        tree.append(layer)

    return MerkleTree(layers=tree)


def get_merkle_root(merkle_tree: MerkleTree) -> bytes:
    """ Returns the root element of the merkle tree. """
    assert merkle_tree.layers, 'the merkle tree layers are empty'
    assert merkle_tree.layers[-1], 'the root layer is empty'

    return merkle_tree.layers[-1][0]
