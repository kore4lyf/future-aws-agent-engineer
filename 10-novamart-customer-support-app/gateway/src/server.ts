import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { config, assertConfiguration } from './config.js';
import api from './routes.js';
import { ApiError } from './errors.js';

const app = express();

app.use(express.json({ limit: '1mb' }));
app.use(cors({ origin: config.corsOrigins, credentials: true }));

// All chat/auth routes live in routes.ts; this file only wires middleware + errors.
app.use('/api', api);

app.use(
  (
    err: unknown,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction
  ) => {
    if (err instanceof ApiError) {
      res.status(err.status).json({
        error: {
          code: err.code,
          message: err.message,
          requiresAuth: err.status === 401,
        },
      });
      return;
    }
    console.error(err);
    res.status(500).json({
      error: { code: 'INTERNAL', message: 'Unexpected server error.' },
    });
  }
);

assertConfiguration();

const PORT = config.port;
app.listen(PORT, () => {
  console.log(`Gateway listening on :${PORT}  mockMode=${config.mockMode}`);
});