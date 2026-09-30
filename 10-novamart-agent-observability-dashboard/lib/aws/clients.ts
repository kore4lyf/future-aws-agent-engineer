import "server-only";

import { CloudWatchLogsClient } from "@aws-sdk/client-cloudwatch-logs";
import { STSClient } from "@aws-sdk/client-sts";
import { XRayClient } from "@aws-sdk/client-xray";

import { readConsoleConfig } from "@/lib/config";

export interface AwsDeps {
  logs: CloudWatchLogsClient;
  sts: STSClient;
  xray: XRayClient;
}

let cached: AwsDeps | undefined;

export function createAwsDeps(): AwsDeps {
  const { region } = readConsoleConfig();
  return {
    logs: new CloudWatchLogsClient({ region }),
    sts: new STSClient({ region }),
    xray: new XRayClient({ region }),
  };
}

export function defaultDeps(): AwsDeps {
  cached ??= createAwsDeps();
  return cached;
}
