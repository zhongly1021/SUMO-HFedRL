import gym
from gym.spaces.space import Space
import numpy as np
import os
import traci

from collections import OrderedDict
from gym import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from typing import Any, Dict, List, Tuple

from .const import *
from .kernel.kernel import SumoKernel
from .sumo_env import SumoEnv
from .utils.random_routes import generate_random_routes


class MultiPolicySumoEnv(SumoEnv, MultiAgentEnv):

    def __init__(self, config):
        super().__init__(config)

    @property
    def multi_action_space(self) -> spaces.Space:
        space = {}
        for index, idx in self.kernel.tls_hub.index2id.items():
            space[idx] = self.kernel.tls_hub[idx].action_space
        return spaces.Dict(space)


    @property
    def action_space(self):
        """This is the action space defined for a *single* traffic light. It is
           defined this way to support RlLib more easily.

        Returns:
            Space: Action space for a single traffic light.
        """
        first = self.kernel.tls_hub.index2id[0]
        return self.kernel.tls_hub[first].action_space


    @property
    def observation_space(self):
        """This is the observation space defined for a *single* traffic light. It is
           defined this way to support RlLib more easily.

        Returns:
            Space: Observation space for a single traffic light.
        """
        first = self.kernel.tls_hub.index2id[0]
        return self.kernel.tls_hub[first].observation_space


    def action_spaces(self, tls_id):
        return self.kernel.tls_hub[tls_id].action_space


    def observation_spaces(self, tls_id):
        return self.kernel.tls_hub[tls_id].observation_space


    def step(self, action_dict: Dict[Any, int]) -> Tuple[Dict, Dict, Dict, Dict]:
        self._do_action(action_dict)
        self.kernel.step()

        obs = self._observe()
        reward = {
            tls.id: self._get_reward(obs[tls.id])
            for tls in self.kernel.tls_hub
        }
        done = {"__all__": self.kernel.done()}
        info = {}

        return obs, reward, done, info


    def _do_action(self, actions: Dict[Any, int]) -> List[int]:
        """Perform the provided action for each trafficlight.

        Args:
            actions (Dict[Any, int]): The action that each trafficlight will take

        Returns:
            List[int]: Returns the action taken -- influenced by which moves are legal or
                not.
        """
        taken_action = actions.copy()
        for tls in self.kernel.tls_hub:
            action = actions[tls.id]
            can_change = self.action_timer.can_change(tls.index)
            if action == 1 and can_change:
                tls.next_phase()
                self.action_timer.restart(tls.index)
            else:
                self.action_timer.decr(tls.index)
                taken_action[tls.index] = 0
        return List[int]


    def _get_reward(self, obs: np.ndarray) -> float:
        """Negative reward function based on the number of halting vehicles, waiting time,
           and travel time.

        Parameters
        ----------
        obs : np.ndarray
            Numpy array (containing float64 values) representing the observation.

        Returns
        -------
        float
            The reward for this step
        """
        # Deprecated.
        # return -obs[NUM_HALT] - obs[WAIT_TIME] - obs[TRAVEL_TIME]
        return -obs[NUM_HALT]


    def _observe(self, ranked: bool=False) -> Dict[Any, np.ndarray]:
        """Get the observations across all the trafficlights, indexed by trafficlight id.

        Returns
        -------
        Dict[Any, np.ndarray]
            Observations from each trafficlight.
        """
        obs = {tls.id: tls.get_observation() for tls in self.kernel.tls_hub}
        if self.ranked: ## NOTE: Should be `self.ranked`, I'm pretty sure.
            self._get_ranks(obs, self.kernel.tls_hub.tls_graph)
        return obs


    def _get_ranks(self, obs: Dict, graph: Dict) -> None:
        """Appends global and local ranks to the observations.

        Args:
            obs (Dict): Observation provided by a trafficlight.
            graph (Dict): Adjacency list of the trafficlight topology.
        """
        pairs = [(tls_id, tls_state[CONGESTION])
                 for tls_id, tls_state in obs.items()]
        pairs = sorted(pairs, key=lambda x: x[1], reverse=True)

        # Calculate the global ranks for each tls in the road network.
        for global_rank, (tls_id, cong) in enumerate(pairs):
            obs[tls_id][GLOBAL_RANK] = 1 - (global_rank / len(graph))

        # Calculate local ranks based on global ranks from above.
        for tls in graph:
            local_rank = 0
            for neighbor in graph[tls]:
                if obs[neighbor][GLOBAL_RANK] > obs[tls][GLOBAL_RANK]:
                    local_rank += 1
            obs[tls][LOCAL_RANK] = 1 - (local_rank / len(graph[tls]))
