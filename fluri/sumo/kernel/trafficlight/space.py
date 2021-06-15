import numpy as np

from fluri.sumo.kernel.const import MAX_MPH_SPEED, NUM_TLS_STATES
from gym.spaces import *
from typing import Any


def trafficlight_space(ranked: bool=False, dtype: Any=np.float32) -> Tuple:
    """This function generates the Tuple state space to support RL in FLURI. State spaces
       generated by this function are meant to be standardized in accordance with the
       configuration file (see `fluri.sumo.kernel.const`). Generated state spaces are
       composed of several different features provided by TraCI (with some postprocessing)
       and rankings if specified via the `ranked` parameter.

    Args:
        ranked (bool, optional): Whether to include ranking features. Defaults to False.
        dtype (Any, optional): Data type for state features. Defaults to np.float32.

    Returns:
        Tuple: Tuple OpenAI gym state space containing all the features.
    """
    # Sub-state spaces for each feature of interest.
    congestion = Box(low=0.0, high=1.0, shape=(1,), dtype=dtype)
    num_halt_vehicles = Box(low=0.0, high=1.0, shape=(1,), dtype=dtype)
    avg_speed = Box(low=0.0, high=1.0, shape=(1,), dtype=dtype)
    curr_state_mode = Discrete(NUM_TLS_STATES)
    curr_state_std = Box(low=0.0, high=NUM_TLS_STATES, shape=(1,), dtype=dtype)

    # Merge the spaces into a single list, then add ranking features (if necessary).
    space_list = [
        congestion,
        num_halt_vehicles,
        avg_speed,
        curr_state_mode,
        curr_state_std
    ]
    if ranked:
        space_list.extend([
            Box(low=0.0, high=1.0, shape=(1,), dtype=dtype),
            Box(low=0.0, high=1.0, shape=(1,), dtype=dtype)
        ])

    # Convert the sub-state spaces for each feature to a tuple and return it as a Space.
    return Tuple(tuple(space_list))
