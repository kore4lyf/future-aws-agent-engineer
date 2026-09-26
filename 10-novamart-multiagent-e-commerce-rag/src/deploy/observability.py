"""
deploy/observability.py
=======================
Task 6 - Observability configuration.

Moved from agent_orchestrator.py lines ~565-590.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from agent_observability import apply_observability_config


__all__ = ['configure_observability']


def configure_observability(runtime_arn: str) -> None:
    """
    Configure observability for the deployed agent:
    - Agent logs -> CloudWatch Logs at INFO level (config.AGENT_LOG_GROUP)
    - Execution traces -> AWS X-Ray at 100% sampling

    The loggingConfiguration built here is applied by
    apply_observability_config() (agent_observability.py):
      cloudWatchConfig -> log group created; runtime env AGENT_LOG_GROUP /
                          AGENT_LOG_LEVEL so the deployed agent ships its logs there
      xRayConfig       -> CloudWatch Transaction Search enabled with the given
                          sampling percentage; runtime env AGENT_TRACING_ENABLED /
                          AGENT_TRACE_SAMPLING_RATE
    """
    # TODO: Build the logging configuration
    # logging_configuration = {
    #     'cloudWatchConfig': {'logGroupName': config.AGENT_LOG_GROUP,
    #                          'logLevel': 'INFO', 'enabled': True},
    #     'xRayConfig':       {'enabled': True, 'samplingRate': 1.0},
    # }
    # Then apply it:  summary = apply_observability_config(runtime_arn, logging_configuration)
    # Wrap the call in try/except - on success print the CloudWatch log group
    # and the X-Ray sampling rate; on exception print
    #   "[Note] Observability configuration failed: <e>"

    pass
