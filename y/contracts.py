import logging
import threading
from functools import lru_cache
from typing import List

from brownie import Contract as _Contract
from brownie import chain, convert, web3
from brownie.exceptions import CompilerError
from multicall import Call, Multicall
from ypricemagic.interfaces.ERC20 import ERC20ABI

from y.exceptions import (ContractNotVerified, call_reverted,
                          contract_not_verified)
from y.networks import Network
from y.utils.cache import memory

logger = logging.getLogger(__name__)


def Contract_erc20(address):
    return _Contract.from_abi('ERC20',address,ERC20ABI)


def Contract_with_erc20_fallback(address):
    try:
        contract = _Contract(address)
    except (AttributeError, CompilerError, IndexError, ValueError):
        contract = Contract_erc20(address)
    return contract


@memory.cache()
def contract_creation_block(address) -> int:
    """
    Determine the block when a contract was created using binary search.
    NOTE Requires access to historical state. Doesn't account for CREATE2 or SELFDESTRUCT.
    """
    logger.info("contract creation block %s", address)
    height = chain.height
    lo, hi = 0, height
    while hi - lo > 1:
        mid = lo + (hi - lo) // 2
        try:
            if web3.eth.get_code(address, block_identifier=mid): hi = mid
            else: lo = mid
        except ValueError as e:
            if 'missing trie node' in str(e):
                logger.critical('missing trie node, `contract_creation_block` may output a higher block than actual. Please try again using an archive node.')
                lo = mid
            else: raise
    return hi if hi != height else None

class Singleton(type):
    def __init__(self, *args, **kwargs):
        self.__instance = None
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self.__instance is None:
            self.__instance = super().__call__(*args, **kwargs)
            return self.__instance
        else:
            return self.__instance

# cached Contract instance, saves about 20ms of init time
_contract_lock = threading.Lock()
_contract = lru_cache(maxsize=None)(_Contract)

def Contract(address):
    with _contract_lock:
        try: return _contract(address)
        except ValueError as e:
            if contract_not_verified(e): raise ContractNotVerified(f'{address} on {Network.printable()}')
            else: raise

@memory.cache()
def is_contract(address: str) -> bool:
    '''
    Checks to see if the input address is a contract. Returns `True` if:
    - The address is not and has never been a contract
    - The address used to be a contract but has self-destructed
    '''
    return web3.eth.get_code(address) != '0x'

@memory.cache()
def has_method(address: str, method: str, return_response: bool = False) -> bool:
    '''
    Checks to see if a contract has a `method` view method with no inputs.
    `return_response=True` will return `response` in bytes if `response` else `False`
    '''
    try: response = Call(address, [f'{method}()()'], [[None, None]], _w3=web3)()
    except Exception as e:
        if call_reverted(e): return False
        raise
    
    if not got_response(response): return False
    if return_response: return response
    return True

@memory.cache()
def has_methods(
    address: str, 
    methods: List[str],
    at_least_one: bool = False
) -> bool:
    '''
    Checks to see if a contract has each view method (with no inputs) in `methods`.
    Pass `at_least_one=True` to only verify a contract has at least one of the methods.
    '''
    func = any if at_least_one else all
    calls = [Call(address, [f'{method}()()'], [[i, None]]) for i, method in enumerate(methods)]
    try: response = Multicall(calls, _w3=web3, require_success=False)().values()
    # We return False here because `has_methods` is only supposed to work for public view methods with no inputs
    # Out of gas error implies method is state-changing
    except ValueError as e:
        if 'out of gas' in str(e): return False 
        else: raise
    
    # sometimes the call won't revert but you don't get anything back
    response = [got_response(data) for data in response]

    return func(response)

def got_response(data) -> bool:
    '''
    Sometimes a call won't revert but you don't get anything back.
    This will validate whether you got a response.
    '''
    if data is None: return False
    if convert.to_string(data) == '': return False
    return True 
    

@memory.cache()
def build_name(address: str, return_None_on_failure: bool = False) -> str:
    try:
        contract = Contract(address)
        return contract.__dict__['_build']['contractName']
    except ContractNotVerified:
        if return_None_on_failure: return None
        else: raise
