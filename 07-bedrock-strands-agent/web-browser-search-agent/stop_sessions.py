import boto3
c = boto3.client('bedrock-agentcore', region_name='us-east-1')
r = c.list_browser_sessions(browserIdentifier='aws.browser.v1')
sessions = r.get('sessions', [])
print(f'found {len(sessions)} sessions')
for s in sessions:
    sid = s.get('sessionId') or s.get('session_id') or s.get('id')
    print('stopping', sid, s.get('status'))
    try:
        print(c.stop_browser_session(browserIdentifier='aws.browser.v1', sessionId=sid))
    except Exception as e:
        print('failed', e)
