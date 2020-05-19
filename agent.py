from itertools import count
import random

import numpy as np

import torch
import torch.optim as optim

from game import Game
from experience_replay import experienceReplay
from dqn import DQN


class Agent():
    
    def __init__(self, game_name, device='cpu'):
        
        #Set hyperparameters
        self.discount = 0.99
        self.learning_rate = 0.00025
        self.batch_size = 32
        self.eps_start = 1
        self.eps_end = 0.1
        self.eps_decay = 1000000
        self.target_update = 10000
        self.num_steps = 50000000
        self.max_episodes = 10000
        
        #Device
        self.device = device

        #Game
        self.game = Game(game_name)
        self.num_actions = self.game.get_n_actions()
        
        #Experience Replay Memory
        self.memory_size = 10000000
        self.memory = experienceReplay(self.memory_size)
        
        #Double Deep Q Network
        self.primary_network = DQN(self.num_actions)
        self.target_network = DQN(self.num_actions)
        self.target_network.load_state_dict(self.primary_network.state_dict())
        self.target_network.eval()
        
        #Loss function
        self.loss_func = torch.nn.MSELoss()
        
        #Optimiser
        self.momentum = 0.95
        self.optimizer = optim.RMSprop(self.primary_network.parameters(), 
                            lr=self.learning_rate, alpha=0.99, eps=1e-08, 
                            weight_decay=0, momentum=self.momentum
                        )
        #clear gradients
        self.optimizer.zero_grad()
        
        
    def select_action(self, steps, state):
        """
            Selects next action to perform using greedy policy. Target network is used to 
            estimate q-values.
            
            Arguments:
                steps - Number of steps performed till now
                state - Current state of atari game, contains last 4 frames. 
        """
        #linear decay of epsilon value
        epsilon = self.eps_start + (self.eps_end - self.eps_start) * (steps / self.eps_decay)
        if random.random() < epsilon:
            #exploration
            return torch.tensor(np.random.choice(np.arange(self.num_actions)))
        else:
            #exploitation
            #use primary_network to estimate q-values of actions
            return torch.argmax(self.primary_network(state.unsqueeze(0)))
        
    
    def batch_train(self):
        """
            Performs batch training on the network. Implements Double Q learning on network. 
            It evaluates greedy policy using primary network but its value is 
            estimated using target network.
            Loss funtion used is Mean Squared Error.
            Uses RMSprop for gradient based optimisation.
        """
        if(self.memory.number_of_experiences() < self.batch_size):
            #Not enough experiences for batch training
            return
        
        #Sample batch from replay memory
        batch_data = self.memory.selectBatch(self.batch_size)
        batch_states, batch_actions, batch_rewards, batch_next_states, done = list(zip(*batch_data))
        
        batch_states = torch.stack(batch_states, dim=0)
        batch_next_states = torch.stack(batch_next_states, dim=0)
        batch_actions = torch.tensor(batch_actions)
        batch_rewards = torch.tensor(batch_rewards)
        not_done = ~torch.tensor(done)
        # batch_states = torch.from_numpy(batch_states).type(torch.float32)
        # batch_actions = torch.from_numpy(batch_actions).type(torch.int32)
        # batch_rewards = torch.from_numpy(batch_rewards).type(torch.float32)
        # batch_next_states = torch.from_numpy(batch_next_state).type(torch.float32)
        # not_done = torch.from_numpy(1 - done).type(torch.int32)

        Q_t_values = self.target_network(batch_states)[:, batch_actions]

        # next_Q_t_primary_values = not_done * self.primary_network(batch_next_states)
        # next_Q_t_target_values = not_done * self.target_network(batch_next_states)
        next_Q_t_primary_values = self.primary_network(batch_next_states)
        next_Q_t_target_values = self.target_network(batch_next_states)

        next_Q_t_values_max = next_Q_t_target_values[:, torch.argmax(next_Q_t_primary_values, axis=1)]
        
        #Double Q-Learning
        expected_Q_values = batch_rewards + (self.discount * next_Q_t_values_max)
        
        #Calulating loss
        loss = self.loss_func(Q_t_values, expected_Q_values)
        
        #Clear gradients from last backward pass
        self.optimizer.zero_grad()
        
        #Run backward pass and calculate gradients
        loss.backward()
        
        #Update weights from calculated gradients
        self.optimizer.step()
        
        
    def train(self):
        steps = 0
        total_reward = 0
        record_rewards = []
        for i in range(self.max_episodes):
            self.game.reset_env()
            state = self.game.get_input()
            for j in count():
                #Update counters
                steps += 1
                
                #Select action using greedy policy
                action = self.select_action(steps, state)
                reward, done = self.game.step(action)
                
                total_reward += reward
                
                if not done:
                        #get the next state
                        next_state = self.game.get_input()
                else:
                    next_state = None
                
                # Convert all arrays to CPU Torch tensor
                state = state.cpu()
                if not done:
                    next_state = next_state.cpu()
                action = action.cpu()
                # reward = torch.tensor(reward)  # 'reward' is left as float
                # done = torch.tensor(done)  # 'done' is left as boolean

                #Store experiences in replay memory for batch training
                if not done:
                    self.memory.storeExperience(state, action, reward, next_state, done)
                
                if done:
                    #Batch Train from experiences if final state is reached
                    self.batch_train()
                    record_rewards.append(total_reward)
                    total_reward = 0
                    break
                        
                #next state assigned to current state
                state = next_state
                
                if(steps % self.target_update == 0):
                    #Update the target_network
                    self.target_network.load_state_dict(self.primary_network.state_dict())
                    self.target_network.eval()
                
                if(steps == self.num_steps):
                    print("Training Done\n")
                    break
            
            if(steps == self.num_steps):
                break
                
        return record_rewards
                
                
