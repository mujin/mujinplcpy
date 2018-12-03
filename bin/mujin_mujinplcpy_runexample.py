#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from mujinplc import plcmemory, plcserver, plccontroller, plclogic

import logging
log = logging.getLogger(__name__)

if __name__ == '__main__':
	logging.basicConfig(format='%(asctime)s %(name)s [%(levelname)s] [%(filename)s:%(lineno)s %(funcName)s] %(message)s', level=logging.DEBUG)

	memory = plcmemory.PLCMemory()
	server = plcserver.PLCServer(memory, 'tcp://*:5555')
	server.Start()
	log.info('server started.')

	controller = plccontroller.PLCController(memory, maxHeartbeatInterval=0.1)
	logic = plclogic.PLCLogic(controller)
	# log.debug('%r', controller.WaitUntilAll({'startOrderCycle': True}))

	logic.WaitUntilConnected()
	log.info('connected.')

	# pause until we want to stop
	# in a real program, should handle SIGTERM instead
	input('Press ENTER to stop.\n')

	server.Stop()
	log.info('server stopped.')
