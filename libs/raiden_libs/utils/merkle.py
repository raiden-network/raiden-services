from collections import namedtuple
from typing import Iterable, Tuple, List
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
    leaves = sorted(items)

    if not all(isinstance(l, bytes) and len(l) == 32 for l in leaves):
        raise ValueError('Not all items are hashes')

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


def is_empty_merkle_root(item: bytes) -> bool:
    """ Returns if the item is the marker for an empty merkle tree. """
    return item == EMPTY_MERKLE_ROOT


def compute_merkle_proof(merkletree: MerkleTree, element: bytes) -> List[bytes]:
    """ Containment proof for element.

    The proof contains only the entries that are sufficient to recompute the
    merkleroot, from the leaf `element` up to `root`.

    Raises:
        IndexError: If the element is not part of the merkletree.
    """
    idx = merkletree.layers[0].index(element)

    proof = []
    for layer in merkletree.layers:
        if idx % 2:
            pair = idx - 1
        else:
            pair = idx + 1

        # with an odd number of elements the rightmost one does not have a pair.
        if pair < len(layer):
            proof.append(layer[pair])

        # the tree is binary and balanced
        idx = idx // 2

    return proof


def validate_merkle_proof(proof: List[bytes], merkleroot: bytes, leaf_element: bytes) -> bool:
    """ Checks that `leaf_element` was contained in the tree represented by
    `merkleroot`.
    """

    hash_ = leaf_element
    for pair in proof:
        hash_ = _hash_pair(hash_, pair)

    return hash_ == merkleroot
