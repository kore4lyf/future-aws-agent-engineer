import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import {
  DynamoDBDocumentClient,
  GetCommand,
  UpdateCommand,
  DeleteCommand,
  ScanCommand,
} from '@aws-sdk/lib-dynamodb';
import { config } from './config.js';

/**
 * Conversation history for the chat UI.
 *
 * The backing table (`HISTORY_TABLE_NAME`) is single-keyed on `session_id`
 * and stores a whole conversation in one item:
 *
 *   session_id      S   partition key, e.g. "sess-abc123"
 *   user_id         S   the Cognito sub that owns this session
 *   title           S   first user message, trimmed
 *   message_count   N   number of messages stored
 *   messages        L   [{ tracking_id, role, content:[...], ... }, ...]
 *   updated_at      S   ISO timestamp of the last write
 *   ttl             N   optional auto-expire
 *
 * One GetItem loads a whole thread; one UpdateItem appends a message. There is
 * no sort key and no index, so per-user listing is a filtered Scan — fine at
 * support-app scale, and a GSI on `user_id` is the documented upgrade path if
 * the table ever grows past a few thousand sessions.
 */

export interface StoredMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
}

export interface StoredSession {
  sessionId: string;
  title: string;
  updatedAt: string;
  messages: StoredMessage[];
}

let docClient: DynamoDBDocumentClient | null = null;

function getClient(): DynamoDBDocumentClient {
  if (!docClient) {
    docClient = DynamoDBDocumentClient.from(new DynamoDBClient({ region: config.awsRegion }), {
      marshallOptions: { removeUndefinedValues: true },
    });
  }
  return docClient;
}

/** History is optional; without a table the gateway runs stateless. */
export function isHistoryEnabled(): boolean {
  return Boolean(config.historyTableName);
}

const table = () => config.historyTableName as string;

/** Normalises the `content` field whatever shape it arrived in.
 *
 * The agent runtime stores content as an array of blocks
 * (`[{ text: "..." }]`), while the chat UI wants a plain string. Both are
 * accepted on read so the table can hold rows written by either side.
 */
function contentToString(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((block) => {
        if (typeof block === 'string') return block;
        if (block && typeof block === 'object') {
          const record = block as Record<string, unknown>;
          if (typeof record.text === 'string') return record.text;
          if (typeof record.content === 'string') return record.content;
        }
        return '';
      })
      .join('');
  }
  return '';
}

function toStoredMessage(item: Record<string, unknown>): StoredMessage | null {
  const role = item.role;
  if (role !== 'user' && role !== 'assistant' && role !== 'system') return null;
  const content = contentToString(item.content);
  if (!content && role !== 'system') return null;
  return {
    id: String(item.tracking_id ?? item.id ?? ''),
    role,
    content,
    createdAt: String(item.created_at ?? item.createdAt ?? new Date(0).toISOString()),
  };
}

/** Loads one session's full conversation, or null when it does not exist. */
export async function getSession(
  userId: string,
  sessionId: string
): Promise<StoredSession | null> {
  if (!isHistoryEnabled()) return null;

  const result = await getClient().send(
    new GetCommand({
      TableName: table(),
      Key: { session_id: sessionId },
    })
  );

  const item = result.Item as Record<string, unknown> | undefined;
  if (!item || item.user_id !== userId) return null;

  const messages: StoredMessage[] = [];
  const raw = item.messages;
  if (Array.isArray(raw)) {
    for (const entry of raw) {
      if (entry && typeof entry === 'object') {
        const message = toStoredMessage(entry as Record<string, unknown>);
        if (message) messages.push(message);
      }
    }
  }

  if (messages.length === 0 && !item.title) return null;

  return {
    sessionId,
    title: String(item.title ?? deriveTitle(messages)),
    updatedAt: String(item.updated_at ?? item.updatedAt ?? new Date(0).toISOString()),
    messages,
  };
}

/** Lists every session owned by a user, newest first. */
export async function listSessions(userId: string): Promise<StoredSession[]> {
  if (!isHistoryEnabled()) return [];

  const result = await getClient().send(
    new ScanCommand({
      TableName: table(),
      FilterExpression: 'user_id = :uid',
      ExpressionAttributeValues: { ':uid': userId },
    })
  );

  const sessions: StoredSession[] = [];
  for (const item of result.Items ?? []) {
    const record = item as Record<string, unknown>;
    const messages: StoredMessage[] = [];
    if (Array.isArray(record.messages)) {
      for (const entry of record.messages) {
        if (entry && typeof entry === 'object') {
          const message = toStoredMessage(entry as Record<string, unknown>);
          if (message) messages.push(message);
        }
      }
    }
    sessions.push({
      sessionId: String(record.session_id ?? ''),
      title: String(record.title ?? deriveTitle(messages)),
      updatedAt: String(record.updated_at ?? record.updatedAt ?? new Date(0).toISOString()),
      messages,
    });
  }

  sessions.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
  return sessions;
}

/** Appends one message to a session, creating the session on first write. */
export async function appendMessage(input: {
  userId: string;
  sessionId: string;
  message: StoredMessage;
  title: string;
}): Promise<void> {
  if (!isHistoryEnabled()) return;

  const now = new Date().toISOString();
  // Stored in the agent-runtime shape so the table stays compatible with any
  // other writer (content as a block array, tracking_id as the turn id).
  const entry = {
    tracking_id: input.message.id,
    role: input.message.role,
    content: [{ text: input.message.content }],
    created_at: input.message.createdAt,
  };

  await getClient().send(
    new UpdateCommand({
      TableName: table(),
      Key: { session_id: input.sessionId },
      UpdateExpression:
        'SET user_id = :uid, #title = :title, updated_at = :now, messages = list_append(if_not_exists(messages, :empty), :msg), message_count = if_not_exists(message_count, :zero) + :one',
      ExpressionAttributeNames: { '#title': 'title' },
      ExpressionAttributeValues: {
        ':uid': input.userId,
        ':title': input.title,
        ':now': now,
        ':empty': [],
        ':msg': [entry],
        ':zero': 0,
        ':one': 1,
      },
    })
  );
}

/** Deletes a session and its conversation. */
export async function deleteSession(userId: string, sessionId: string): Promise<void> {
  if (!isHistoryEnabled()) return;

  // Ownership check first: a user can only delete their own session.
  const session = await getSession(userId, sessionId);
  if (!session) return;

  await getClient().send(
    new DeleteCommand({
      TableName: table(),
      Key: { session_id: sessionId },
    })
  );
}

export function deriveTitle(messages: StoredMessage[]): string {
  const firstUser = messages.find((m) => m.role === 'user');
  if (!firstUser) return 'New conversation';
  const single = firstUser.content.replace(/\s+/g, ' ').trim();
  return single.length > 60 ? `${single.slice(0, 60)}…` : single;
}