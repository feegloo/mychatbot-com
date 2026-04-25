# node migration boilerplate

Minimal Koa app used as a migration target that imports code from `backend` as a library.

## Run

```bash
cd node
npm install
npm run dev
```

## Endpoint

- `GET /hello` -> returns message from `backend/src/library/hello-world.ts`

## Tests (Vitest)

- Unit: `npm run test:unit`
- Integration: `npm run test:integration`
- E2E: `npm run test:e2e`
- All: `npm test`

Example response:

```json
{
  "message": "Hello from backend library module"
}
```
