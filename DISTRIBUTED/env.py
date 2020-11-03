import gym
from gym.spaces import Box
import numpy as np
import matlab
import matlab.engine

class DistributedTSCSEnv(gym.Env):
	def __init__(self, config):
		## Initialize matlab
		self.eng = matlab.engine.start_matlab()
		self.eng.addpath('../DDPG/TSCS')

		## Env hyperparameters
		self.nCyl = config['nCyl']
		self.nFreq = config['nFreq']
		self.M = matlab.double([self.nCyl])
		self.k0amax = matlab.double([config['k0amax']])
		self.k0amin = matlab.double([config['k0amin']])
		self.F = matlab.double([self.nFreq])
		self.actionRange = config['actionRange']
		self.episodeLength = config['episodeLength']

		## State variables
		self.config = None
		self.TSCS = None
		self.RMS = None
		self.timestep = None
		self.lowest = None
		self.numIllegalMoves = None

		## Observation and action space
		self.observation_space = Box(
			low=-100.,
			high=100.,
			## Number of cylinders + number of wavenumbers + 2 additional variables (rms, timestep)
			shape=((1, self.nCyl * 2 + self.nFreq + 2)))

		self.action_space = Box(
			low=-self.actionRange,
			high=self.actionRange,
			shape=(self.nCyl * 2,))

	def validConfig(self, config):
		"""
		Checks if config is within bounds and does not overlap cylinders
		"""
		withinBounds = False
		overlap = False
		if (-5 < config).all() and (config < 5).all():
			withinBounds = True

			coords = config.reshape(self.nCyl, 2)
			for i in range(self.nCyl):
				for j in range(self.nCyl):
					if i != j:
						x1, y1 = coords[i]
						x2, y2 = coords[j]
						d = np.sqrt((x2-x1)**2 + (y2-y1)**2)
						if d <= 2.1:
							overlap = True
		return withinBounds and not overlap

	def getConfig(self):
		"""
		Generates a configuration which is within bounds 
		and not overlaping cylinders
		"""
		while True:
			config = np.random.uniform(-5., 5., (1, self.nCyl * 2))
			if self.validConfig(config):
				break
		return config

	def getMetric(self, config):
		"""
		This calculates total cross secitonal scattering across nFreq wavenumbers
		from k0amax to k0amin. Also calculates RMS of these wavenumbers.
		"""
		# x = self.eng.transpose(matlab.double(*self.config.reshape(self.nCyl * 2)))
		x = self.eng.transpose(matlab.double(*config.tolist()))
		tscs = self.eng.getMetric(x, self.M, self.k0amax, self.k0amin, self.F)
		tscs = np.array(tscs).T
		rms = np.sqrt(np.power(tscs, 2).mean()).reshape(1, 1)
		return tscs, rms

	def reset(self):
		"""
		Generates starting config and calculates its tscs
		"""
		self.numIllegalMoves = 0
		self.config = self.getConfig()
		self.TSCS, self.RMS = self.getMetric(self.config)
		self.timestep = np.array([[0.0]])
		self.lowest = self.RMS.item()
		state = np.concatenate((self.config, self.TSCS, self.RMS, self.timestep), axis=-1)
		return state

	def getReward(self, RMS, isValid):
		"""
		Computes reward based on change in scattering 
		proporitional to how close it is to zero
		"""
		reward = -RMS.item()
		if not isValid:
			reward += -1.0
		return reward

	def step(self, action):
		"""
		If the config after applying the action is not valid
		we revert back to previous state and give negative reward
		otherwise, reward is calculated by a function on the next scattering.
		"""
		nextConfig = self.config.copy() + action

		valid = False
		if self.validConfig(nextConfig):
			self.config = nextConfig
			valid = True
		else:
			self.numIllegalMoves += 1

		self.TSCS, self.RMS = self.getMetric(self.config)
		reward = self.getReward(self.RMS, valid)
		self.timestep += 1/self.episodeLength

		if self.RMS < self.lowest:
			self.lowest = self.RMS.item()

		done = False
		if int(self.timestep) == 1:
			done = True

		info = {
			'meanTSCS':self.TSCS.mean(),
			'rms':self.RMS,
			'lowest':self.lowest,
			'numIllegalMoves': self.numIllegalMoves}

		state = np.concatenate((self.config, self.TSCS, self.RMS, self.timestep), axis=-1)
		return state, reward, done, info

if __name__ == '__main__':
	import time

	config = {
		'nCyl':4,
		'k0amax':0.5,
		'k0amin':0.3,
		'nFreq':11,
		'actionRange':0.2,
		'episodeLength':100}

	env = DistributedTSCSEnv(config)

	start = time.time()

	state = env.reset()
	done = False
	while not done:
		action = env.action_space.sample()
		state, reward, done, info = env.step(action)

	print(f'Episode took: {time.time() - start} seconds')