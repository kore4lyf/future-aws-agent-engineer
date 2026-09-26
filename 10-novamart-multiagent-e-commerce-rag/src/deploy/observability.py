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
from agent_observability import apply_observability_config, ENV_LOG_GROUP, ENV_LOG_LEVEL, ENV_LOG_TO_CLOUDWATCH, ENV_TRACING_ENABLED, ENV_SAMPLING_RATE


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
    logging_configuration = {
        'cloudWatchConfig': {
            'logGroupName': config.AGENT_LOG_GROUP,
            'logLevel': 'INFO',
            'enabled': True,
        },
        'xRayConfig': {
            'enabled': True,
            'samplingRate': 1.0,
        },
    }

    try:
        summary = apply_observability_config(runtime_arn, logging_configuration)
        cw = summary.get('runtime_env', {})
        print(f"  CloudWatch: {cw.get(ENV_LOG_GROUP, config.AGENT_LOG_GROUP)} [{cw.get(ENV_LOG_LEVEL, 'INFO')}]")
        print(f"  X-Ray: enabled, samplingRate={cw.get(ENV_SAMPLING_RATE, '1.0')}")
    except Exception as e:
        print(f"[Note] Observability configuration failed: {e}")
