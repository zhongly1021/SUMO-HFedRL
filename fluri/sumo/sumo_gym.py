import gym
import numpy as np
import random
import time
import traci

from collections import defaultdict
from gym import spaces

from . import sumo_util as utils
from .const import *
from .sumo_sim import SumoSim

from typing import Any, Dict, List, Tuple

GUI_DEFAULT = True

class TrafficLights:

    def __init__(self, sim: SumoSim):
        self.sim = sim
        self.ids = self.sim.get_traffic_light_ids()
        self.states = self.sim.get_all_possible_tls_states()
        self.network = utils.make_tls_state_network(self.states)
        self.num = len(self.ids)
        self.curr_states = self.random_states()

        # TODO: Currenlty not being considered.
        self.radii = None

    def random_states(self):
        states = {}
        for tls_id in self.ids:
            states[tls_id] = random.choice([
                self.network.nodes[u]["state"] for u in self.network.neighbors(tls_id)
            ])
        return states

    def update_curr_states(self):
        self.curr_states = self.sim.get_all_curr_tls_states()


class SumoGym(gym.Env):
    """Custom Gym environment designed for simple RL experiments using SUMO/TraCI."""
    metadata = {"render.modes": ["sumo", "sumo-gui"]}
    name = "SUMO-v1"
    GRID_KEY = "grid"
    TLS_KEY  = "traffic_lights"
    
    def __init__(self, sim: SumoSim, grid_shape: Tuple[int, int]=None):
        self.sim = sim
        self.grid_shape = grid_shape
        self.reset()

    def step(self, action: List[int]) -> Tuple[np.ndarray, float, bool, dict]:
        """Performs a single step in the environment, as per the Open AI Gym framework.

        Parameters
        ----------
        action : List[int]
            The action to be taken by each traffic light in the road network.

        Returns
        -------
        Tuple[np.ndarray, float, bool, dict]
            The current observation, reward, if the simulation is done, and other info.
        """
        taken_action = self.__do_action(action)
        traci.simulationStep()

        observation = self.__get_observation()
        reward = self.__get_reward()
        done = self.sim.done()
        info = {"taken_action": taken_action}

        return observation, reward, done, info

    def reset(self) -> Dict[str, Any]:
        """Start a fresh instance of the SumoGym environment.

        Returns
        -------
        Dict[str, Any]
            Current observation of the newly reset environment.
        """
        self.start()
        self.trafficlights = TrafficLights(self.sim)
        self.mask = (-2 * MIN_DELAY) * np.ones(shape=(self.trafficlights.num))
        self.bounding_box = self.sim.get_bounding_box()
        return self.__get_observation()


    def __interpret_action(self, tls_id: str, action: List[int]) -> str:
        """Actions  are passed in as a numpy  array of integers. However, this needs to be
           interpreted as an action state (e.g., `GGrr`) based on the TLS possible states.
           So,  given an ID  tls=2 and  an action  a=[[1], [3], [0], ..., [2]] (where each 
           integer  value  corresponds with  the index  of the  states for a given traffic 
           light), return the state corresponding to the index provided by action.

        Parameters
        ----------
        tls_id : str
            ID of the designated traffic light.
        action : List[int]
            Action vector where each element selects the action for the respective traffic
            light.

        Returns
        -------
        str
            The string state that corresponds with the selected action for the given
            traffic light.
        """
        return self.trafficlights.states[tls_id][action[int(tls_id)]]


    def __do_action(self, action: List[int]) -> List[int]:
        """TODO"""
        can_change = self.mask == 0
        taken_action = action.copy()

        for tls_id, curr_action in self.trafficlights.curr_states.items():
            next_action = self.__interpret_action(tls_id, action)

            curr_node = utils.get_node_id(tls_id, curr_action)
            next_node = utils.get_node_id(tls_id, next_action)
            is_valid = next_node in self.trafficlights.network.neighbors(curr_node)

            if curr_action != next_action and is_valid and can_change[int(tls_id)]:
                traci.trafficlight.setRedYellowGreenState(tls_id, next_action)
                self.mask[int(tls_id)] = -2 * MIN_DELAY

            else:
                traci.trafficlight.setRedYellowGreenState(tls_id, curr_action)
                self.mask[int(tls_id)] = min(0, self.mask[int(tls_id)] + 1)
                taken_action[int(tls_id)] = self.trafficlights.states[tls_id].\
                                            index(curr_action)

        self.trafficlights.update_curr_states()
        return taken_action


    def __get_observation(self) -> Dict[np.ndarray, np.ndarray]:
        """Returns the current observation of the state space, represented by the grid
           space for recognizing vehicle locations and the current state of all traffic
           lights.

        Returns
        -------
        Dict[np.ndarray, np.ndarray]
            Get the current observation of the environment.
        """
        sim_h, sim_w = self.get_sim_dims()
        obs_h, obs_w = self.get_obs_dims()

        h_scalar = obs_h / sim_h
        w_scalar = obs_w / sim_w

        obs = {
            self.GRID_KEY: np.zeros(shape=(obs_h, obs_w), dtype=np.int32),
            self.TLS_KEY:  np.zeros(shape=(self.trafficlights.num), dtype=np.int32)
        }

        veh_ids = list(traci.vehicle.getIDList())
        
        for veh_id in veh_ids:
            # Get the (scaled-down) x/y coordinates for the observation grid.
            x, y = traci.vehicle.getPosition(veh_id)
            x = int(x * w_scalar)
            y = int(y * h_scalar)

            # Add a normalized weight to the respective coordinate in the grid. For it to
            # be normalized, we need to change `dtype` to a float-based value.
            obs[self.GRID_KEY][y, x] += 1 #/ len(veh_ids)

        for tls_id, curr_state in self.trafficlights.curr_states.items():
            index = self.trafficlights.states[tls_id].index(curr_state)
            obs[self.TLS_KEY][int(tls_id)] = index

        return obs[self.GRID_KEY]
        # return obs


    def __get_reward(self) -> float:
        """TODO"""
        done = self.sim.done()
        return -1.0 if not done else 0.0


    

    def close(self) -> None:
        self.sim.close()

    def start(self) -> None:
        self.sim.start()


    def get_sim_dims(self) -> Tuple[int, int]:
        """Provides the original (height, width) dimensions for the simulation for this
           Gym environment.

        Returns
        -------
        Tuple[int, int]
            (width, height) of SumoGym instance.
        """
        x_min, y_min, x_max, y_max = self.bounding_box
        width = int(x_max - x_min)
        height = int(y_max - y_min)
        return (height, width)

    def get_obs_dims(self) -> Tuple[int, int]:
        """Gets the dimensions of the grid observation space. If the `grid_shape` param
           is set to None, then the original bounding box's dimensions (provided by TraCI)
           will be used. This, however, is non-optimal and it is recommended that you
           provide a smaller dimensionality to represent the `grid_shape` for better
           learning.

        Returns
        -------
        Tuple[int, int]
            (height, width) pair of the observation space.
        """
        if self.grid_shape is None:
            return self.get_sim_dims()
        else:
            return self.grid_shape


    @property
    def action_space(self):
        """Initializes an instance of the action space as a property of the class."""
        ## TODO: We need to adjust the `sample()` function for this action_space such that
        ##       it restricts available actions based on the current action.
        return spaces.MultiDiscrete([
            len(self.trafficlights.states[tls_id]) 
            for tls_id in self.trafficlights.states
        ])


    @property
    def observation_space(self):
        """Initializes an instance of the observation space as a property of the class."""
        grid_space = spaces.Box(
            low=0, 
            high=10, 
            shape=self.get_obs_dims(),
            dtype=np.int8
        )
        return grid_space

        tls_space = spaces.MultiDiscrete([
            len(self.trafficlights.states[tls_id]) 
            for tls_id in self.trafficlights.states
        ])
        return spaces.Dict({
            self.GRID_KEY: grid_space, 
            self.TLS_KEY:  tls_space
        })