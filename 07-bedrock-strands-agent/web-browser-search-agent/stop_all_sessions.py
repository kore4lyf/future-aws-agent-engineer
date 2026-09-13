import boto3
ctl = boto3.client('bedrock-agentcore-control', region_name='us-east-1')
rt = boto3.client('bedrock-agentcore', region_name='us-east-1')
browsers = ctl.list_browsers().get('browsers', [])
print(f'browsers: {len(browsers)}')
for b in browsers:
    bid = b.get('browserId') or b.get('browser_id')
    print('browser', bid)
    token = None
    while True:
        kw = {'browserIdentifier': bid}
        if token:
            kw['nextToken'] = token
        r = rt.list_browser_sessions(**kw)
        sessions = r.get('sessions', [])
        for s in sessions:
            sid = s.get('sessionId')
            status = s.get('status')
            if status and status.upper() != 'TERMINATED':
                print('stopping', sid, status)
                try:
                    rt.stop_browser_session(browserIdentifier=bid, sessionId=sid)
                    print('stopped', sid)
                except Exception as e:
                    print('failed', sid, e)
        token = r.get('nextToken')
        if not token:
            break
print('done')
