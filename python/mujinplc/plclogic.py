# -*- coding: utf-8 -*-

import enum

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

    _errorCode = None
    _errorDetail = None

    def __init__(self, errorCode=PLCErrorCode.GenericError, errorDetail=''):
        self._errorCode = errorCode
        self._errorDetail = errorDetail

    def GetErrorCode(self):
        """
        MUJIN PLC Error Code
        """
        return self._errorCode

    def GetErrorDetail(self):
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

class PLCLogic:
    """
    MUJIN specific PLC logic implementation.
    """

    _controller = None # an instance of PLCController

    def __init__(self, controller):
        self._controller = controller

    def ClearAllSignals(self):
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

    def WaitUntilConnected(self, timeout=None):
        """
        Block until connection from MUJIN controller is detected.
        """
        return self._controller.WaitUntilConnected(timeout=timeout)

    def IsError(self):
        """
        Whether MUJIN controller is in error.
        """
        return self._controller.GetBoolean('isError')

    def CheckError(self):
        """
        Check if there is an error set by MUJIN controller in the current state. If so, raise a PLCError exception. 
        """
        if self.IsError():
            errorCode = PLCErrorCode(self._controller.GetInteger('errorcode'))
            errorDetail = self._controller.GetString('detailedErrorCode')
            raise PLCError(errorCode, errorDetail)

    def ResetError(self, timeout=None):
        """
        Reset error on MUJIN controller. Block until error is reset.
        """
        self._controller.Set('resetError', True)
        try:
            if not self._controller.WaitUntil('isError', False, timeout=timeout):
                raise PLCWaitTimeout()
        finally:
            self._controller.Set('resetError', False)

    def WaitUntilOrderCycleReady(self, timeout=None):
        """
        Block until MUJIN controller is ready to start order cycle.
        """
        if not self._controller.WaitUntil({
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

    def StartOrderCycle(self, startOrderCycleParameters, timeout=None):
        """
        Start order cycle. Block until MUJIN controller acknowledge the start command.
        """
        pass

    def GetOrderCycleStatus(self):
        """
        Gather order cycle status information in the current state.
        """
        pass

    def WaitForOrderCycleStatusChange(self, timeout=None):
        """
        Block until values in order cycle status changes.
        """
        pass

    def WaitUntilOrderCycleFinish(self, timeout=None):
        """
        Block until MUJIN controller finishes the order cycle.
        """
        pass

    def StopOrderCycle(self, timeout=None):
        """
        Signal MUJIN controller to stop order cycle and block until it is stopped.
        """
        pass

    def StopImmediately(self, timeout=None):
        """
        Stop the current operation on MUJIN controller immediately.
        """
        pass

    def WaitUntilMoveToHomeReady(self, timeout=None):
        """
        Block until MUJIN controller is ready to move robot to home position.
        """
        pass

    def StartMoveToHome(self, timeout=None):
        """
        Signal MUJIN controller to move the robot to its home position. Block until the robot starts moving.
        """
        pass

    def WaitUntilRobotMoving(self, timeout=None):
        """
        Block until the robot moving state is expected.
        """
        pass

    