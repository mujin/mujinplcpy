# -*- coding: utf-8 -*-

import typing
import enum

from . import plccontroller

class PLCWaitTimeout(Exception):
    pass

class PLCErrorCode(enum.Enum):
    """
    MUJIN PLC ErrorCode
    """

    ErrorCodeNotAvailable = 0x0000
    EStopError = 0x1000
    PLCError = 0x2000
    PLCSupplyInterlockError = 0x2001
    PLCDestInterlockError = 0x2002
    PLCOtherInterlockError = 0x2003
    PLCCommandError = 0x2010
    PlanningError = 0x3000
    DetectionError = 0x4000
    SensorError = 0x5000
    RobotError = 0x6000
    SystemError = 0x7000
    OtherCycleError = 0xf000
    InCycleError = 0xf001
    InvalidOrderNumberError = 0xf003
    NotRunningError = 0xf004
    FailedToMoveToError = 0xf009
    GenericError = 0xffff

class PLCError(Exception):
    """
    PLCError is raised when an error code is set by MUJIN controller.
    """

    _errorCode = None # type: PLCErrorCode
    _errorDetail = None # type: str

    def __init__(self, errorCode: PLCErrorCode = PLCErrorCode.GenericError, errorDetail: str = ''):
        self._errorCode = errorCode
        self._errorDetail = errorDetail

    def GetErrorCode(self) -> PLCErrorCode:
        """
        MUJIN PLC Error Code
        """
        return self._errorCode

    def GetErrorDetail(self) -> str:
        """
        When ErrorCode is RobotError, ErrorDetail contains the error code returned by robot controller.
        """
        return self._errorDetail

class PLCOrderCycleFinishCode(enum.Enum):
    """
    MUJIN PLC OrderCycleFinishCode
    """

    FinishedNotAvailable = 0x0000
    FinishedOrderComplete = 0x0001
    FinishedNoMoreTargets = 0x0002
    FinishedNoMoreTargetsNotEmpty = 0x0003
    FinishedNoMoreDest = 0x0004
    FinishedNoEnvironmentUpdate = 0x0005
    FinishedDropTargetFailure = 0x0006
    FinishedTooManyPickFailures = 0x0007
    FinishedRobotExecutionError = 0x0008
    FinishedNoDestObstacles = 0x0009
    FinishedStopped = 0x0101
    FinishedStoppedImmediately = 0x0102
    FinishedPlanningFailure = 0x1000
    FinishedNoValidGrasp = 0x1001
    FinishedNoValidDest = 0x1002
    FinishedNoValidGraspDestPair = 0x1003
    FinishedNoValidPath = 0x1004
    FinishedNoValidTargets = 0x1005
    FinishedNoValidBarcodeScan = 0x1006
    FinishedComputePlanFailure = 0x1007
    FinishedCannotGenerateGraspingModel = 0x1008
    FinishedContainerNotDetected = 0x2001
    FinishedPlaceContainerNotDetected = 0x2002
    FinishedBadExpectedDetectionHeight = 0x2003
    FinishedCannotComputeFinishPlan = 0xfff7
    FinishedUnknownReasonNoError = 0xfff8
    FinishedCannotGetState = 0xfff9
    FinishedCycleStopCanceled = 0xfffa
    FinishedDropOffIsOn = 0xfffb
    FinishedBadPartType = 0xfffd
    FinishedBadOrderCyclePrecondition = 0xfffe
    FinishedGenericFailure = 0xffff

class PLCPreparationFinishCode(enum.Enum):
    PreparationNotAvailable = 0x0000
    PreparationFinishedSuccess = 0x0001
    PreparationFinishedImmediatelyStopped = 0x0102
    PreparationFinishedBadPartType = 0xfffd
    PreparationFinishedBadOrderCyclePrecondition = 0xfffe
    PreparationFinishedGenericError = 0xffff

class PackComputationFinishCode(enum.Enum):
    FinishedPackingUnknown = 0x0000
    FinishedPackingSuccess = 0x0001
    FinishedPackingInvalid = 0x0002
    FinishedPackingStopped = 0x0102
    FinishedCannotGetState = 0xfff9
    FinishedBadOrderCyclePrecondition = 0xfffe
    FinishedPackingError = 0xffff

class PLCOrderCycleStatus:
    isRunningOrderCycle = False # type: bool # whether the order cycle is currently running
    isRobotMoving = False # type: bool # whether the robot is currently moving
    numLeftInOrder = 0 # type: int # number of items left in order to be picked
    numPlacedInDest = 0 # type: int # number of items placed in destination container
    orderCycleFinishCode = PLCOrderCycleFinishCode.FinishedNotAvailable # type: PLCOrderCycleFinishCode # finish code of order cycle

class PLCStartOrderCycleParameters:
    partType = '' # type: str # type of the product to be picked, for example: "cola"
    orderNumber = 0 # type: int # number of items to be picked, for example: 1
    robotId = 0 # type: int # set to 1

    pickLocationIndex = 0 # type: int # index of location for source container, location defined on mujin pendant
    pickContainerId = '' # type: str # barcode of the source container, for example: "010023"
    pickContainerType = '' # type: str # type of the source container, if all the same, set to ""

    placeLocationIndex = 0 # type: int # index of location for dest container, location defined on mujin pendant
    placeContainerId = '' # type: str # barcode of the dest contianer, for example: "pallet1"
    placeContainerType = '' # type: str # type of the source container, if all the same, set to ""

class PLCLogic:
    """
    MUJIN specific PLC logic implementation.
    """

    _controller = None # type: plccontroller.PLCController # an instance of PLCController

    def __init__(self, controller: plccontroller.PLCController):
        self._controller = controller

    def ClearAllSignals(self) -> None:
        """
        Clear all signals to the MUJIN controller. Set them all to false.
        """
        self._controller.SetMultiple({
            'startOrderCycle': False,
            'stopOrderCycle': False,
            'stopImmediately': False,
            'startPreparation': False,
            'stopPreparation': False,
            'startMoveToHome': False,
            'startDetection': False,
            'stopDetection': False,
            'stopGripper': False,
            'resetError': False,
        })

    def WaitUntilConnected(self, timeout: typing.Optional[float] = None) -> None:
        """
        Block until connection from MUJIN controller is detected.
        """
        if not self._controller.WaitUntilConnected(timeout=timeout):
            raise PLCWaitTimeout()

    def IsError(self) -> bool:
        """
        Whether MUJIN controller is in error.
        """
        return self._controller.GetBoolean('isError')

    def CheckError(self) -> None:
        """
        Check if there is an error set by MUJIN controller in the current state. If so, raise a PLCError exception. 
        """
        if self.IsError():
            errorCode = PLCErrorCode(self._controller.GetInteger('errorcode'))
            errorDetail = self._controller.GetString('detailedErrorCode')
            raise PLCError(errorCode, errorDetail)

    def ResetError(self, timeout: typing.Optional[float] = None) -> None:
        """
        Reset error on MUJIN controller. Block until error is reset.
        """
        self._controller.Set('resetError', True)
        try:
            if not self._controller.WaitUntil('isError', False, timeout=timeout):
                raise PLCWaitTimeout()
        finally:
            self._controller.Set('resetError', False)

    def WaitUntilOrderCycleReady(self, timeout: typing.Optional[float] = None) -> None:
        """
        Block until MUJIN controller is ready to start order cycle.
        """
        if not self._controller.WaitUntilAll({
            'isRunningOrderCycle': False,
            'isRobotMoving': False,
            'isModeAuto': True,
            'isSystemReady': True,
            'isCycleReady': True,
        }, {
            'isError': True,
        }, timeout=timeout):
            raise PLCWaitTimeout()
        self.CheckError()

    def StartOrderCycle(self, startOrderCycleParameters: PLCStartOrderCycleParameters, timeout: typing.Optional[float] = None) -> PLCOrderCycleStatus:
        """
        Start order cycle. Block until MUJIN controller acknowledge the start command.
        """
        self._controller.SetMultiple({
            'orderPartType': startOrderCycleParameters.partType,
            'orderNumber': startOrderCycleParameters.orderNumber,
            'orderRobotId': startOrderCycleParameters.robotId,
            'orderPickLocationIndex': startOrderCycleParameters.pickLocationIndex,
            'orderPickContainerId': startOrderCycleParameters.pickContainerId,
            'orderPickContainerType': startOrderCycleParameters.pickContainerType,
            'orderPlaceLocationIndex': startOrderCycleParameters.placeLocationIndex,
            'orderPlaceContainerId': startOrderCycleParameters.placeContainerId,
            'orderPlaceContainerType': startOrderCycleParameters.placeContainerType,
            'startOrderCycle': True,
        })
        try:
            if not self._controller.WaitUntilAll({
                'isRunningOrderCycle': True,
            }, {
                'isError': True,
            }, timeout=timeout):
                raise PLCWaitTimeout()
        finally:
            self._controller.Set('startOrderCycle', False)
        self.CheckError()
        return self.GetOrderCycleStatus()

    def GetOrderCycleStatus(self) -> PLCOrderCycleStatus:
        """
        Gather order cycle status information in the current state.
        """
        status = PLCOrderCycleStatus()
        status.isRunningOrderCycle = self._controller.GetBoolean('isRunningOrderCycle')
        status.isRobotMoving = self._controller.GetBoolean('isRobotMoving')
        status.numLeftInOrder = self._controller.GetInteger('numLeftInOrder')
        status.numPlacedInDest = self._controller.GetInteger('numPlacedInDest')
        status.orderCycleFinishCode = PLCOrderCycleFinishCode(self._controller.GetInteger('orderCycleFinishCode'))
        return status

    def WaitForOrderCycleStatusChange(self, timeout: typing.Optional[float] = None) -> PLCOrderCycleStatus:
        """
        Block until values in order cycle status changes.
        """
        self._controller.WaitForAny({
            'isError': True,

            # listen to any changes in the following addresses
            'isRunningOrderCycle': None,
            'isRobotMoving': None,
            'numLeftInOrder': None,
            'numPlacedInDest': None,
            'orderCycleFinishCode':  None,
        })
        self.CheckError()
        return self.GetOrderCycleStatus()

    def WaitUntilOrderCycleFinish(self, timeout: typing.Optional[float] = None) -> PLCOrderCycleStatus:
        """
        Block until MUJIN controller finishes the order cycle.
        """
        if not self._controller.WaitUntilAll({
            'isRunningOrderCycle': False,
        }, {
            'isError': True,
        }, timeout=timeout):
            raise PLCWaitTimeout()
        self.CheckError()
        return self.GetOrderCycleStatus()

    def StopOrderCycle(self, timeout: typing.Optional[float] = None) -> PLCOrderCycleStatus:
        """
        Signal MUJIN controller to stop order cycle and block until it is stopped.
        """
        self._controller.Set('stopOrderCycle', True)
        try:
            if not self._controller.WaitUntilAll({
                'isRunningOrderCycle': False,
            }, {
                'isError': True,
            }, timeout=timeout):
                raise PLCWaitTimeout()
        finally:
            self._controller.Set('startOrderCycle', False)
        self.CheckError()
        return self.GetOrderCycleStatus()

    def StopImmediately(self, timeout: typing.Optional[float] = None) -> None:
        """
        Stop the current operation on MUJIN controller immediately.
        """
        self._controller.Set('stopImmediately', True)
        try:
            if not self._controller.WaitUntilAll({
                'isRunningOrderCycle': False,
                'isRobotMoving':  False,
            }, {
                'isError': True,
            }, timeout=timeout):
                raise PLCWaitTimeout()
        finally:
            self._controller.Set('stopImmediately', False)
        self.CheckError()

    def WaitUntilMoveToHomeReady(self, timeout: typing.Optional[float] = None) -> None:
        """
        Block until MUJIN controller is ready to move robot to home position.
        """
        if not self._controller.WaitUntilAll({
            'isRunningOrderCycle': False,
            'isRobotMoving': False,
            'isModeAuto': True,
            'isSystemReady': True,
        }, {
            'isError': True,
        }, timeout=timeout):
            raise PLCWaitTimeout()
        self.CheckError()

    def StartMoveToHome(self, timeout: typing.Optional[float] = None) -> None:
        """
        Signal MUJIN controller to move the robot to its home position. Block until the robot starts moving.
        """
        self._controller.Set('startMoveToHome', True)
        try:
            if not self._controller.WaitUntilAll({
                'isRobotMoving': True,
            }, {
                'isError': True,
            }, timeout=timeout):
                raise PLCWaitTimeout()
        finally:
            self._controller.Set('startMoveToHome', False)
        self.CheckError()

    def WaitUntilRobotMoving(self, isRobotMoving: bool = True, timeout: typing.Optional[float] = None) -> None:
        """
        Block until the robot moving state is expected.
        """
        if not self._controller.WaitUntilAll({
            'isRobotMoving': isRobotMoving,
        }, {
            'isError': True,
        }, timeout=timeout):
            raise PLCWaitTimeout()
        self.CheckError()
