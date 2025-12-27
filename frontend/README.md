# NPL Approval Dashboard (NPL-Native Frontend)

Type-safe React frontend for the NPL approval workflow, using auto-generated clients from OpenAPI specifications.

## Architecture

- **Type-Safe API Clients**: Generated from NPL Engine OpenAPI specs using `openapi-typescript`
- **Authentication**: Keycloak integration with React
- **Direct NPL Communication**: No backend proxy - talks directly to NPL Engine

## Setup

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env.development
   ```
   
   Edit `.env.development` if needed (defaults are already configured for local development).

3. **Regenerate types** (when protocols change):
   ```bash
   # Download latest OpenAPI spec
   curl -s http://localhost:12000/npl/commerce/-/openapi.json > openapi/commerce-openapi.json
   
   # Regenerate TypeScript types
   npx openapi-typescript openapi/commerce-openapi.json -o ./src/clients/commerce/types.ts
   ```

4. **Run development server**:
   ```bash
   npm run dev
   ```

Access at `http://localhost:5173`

## Benefits

- ✅ **Auto-generated types** - Never out of sync with protocols
- ✅ **Type-safe API calls** - Compile-time verification
- ✅ **Direct NPL integration** - No proxy layer needed
- ✅ **Automatic Keycloak auth** - Built-in authentication handling
