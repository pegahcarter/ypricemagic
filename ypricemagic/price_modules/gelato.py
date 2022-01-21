from functools import lru_cache

import ypricemagic.magic
from y.contracts import has_methods
from ypricemagic.utils.raw_calls import (_decimals, _totalSupplyReadable,
                                         raw_call)


@lru_cache
def is_gelato_pool(token_address: str) -> bool:
    return has_methods(token_address, ['gelatoBalance0()(uint)','gelatoBalance1()(uint)'])

def get_price(token_address: str, block=None):
    token0 = raw_call(token_address,'token0()',block=block,output='address')
    token1 = raw_call(token_address,'token1()',block=block,output='address')
    balance0 = raw_call(token_address,'gelatoBalance0()',block=block,output='int')
    balance1 = raw_call(token_address,'gelatoBalance1()',block=block,output='int')
    balance0 /= 10 ** _decimals(token0,block)
    balance1 /= 10 ** _decimals(token1,block)
    totalSupply = _totalSupplyReadable(token_address,block)
    totalVal = balance0 * ypricemagic.magic.get_price(token0,block) + balance1 * ypricemagic.magic.get_price(token1,block)
    return totalVal / totalSupply
