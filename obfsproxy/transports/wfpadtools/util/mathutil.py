import math


def closest_multiple(n, k, ceil=True):
    """Return closest greater multiple of `k` to `n`."""
    if n == 0:
        return 0
    if n < k:
        return k
    if n % k == 0:
        return n
    return k * (n / k + (1 if ceil else 0))


def closest_power_of_two(n, ceil=True):
    """Return closest greater power of two to `n`."""
    if n < 0:
        raise ValueError("Operation not permitted with negative values.")
    if n == 0 or n == 1:
        return 2
    k = math.ceil(math.log(float(n), 2))
    return int(math.pow(2, k))
