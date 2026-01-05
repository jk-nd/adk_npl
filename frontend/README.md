# ADK-NPL Dashboard Frontend

React + TypeScript dashboard for the ADK-NPL demo, featuring agent chat interfaces, approval workflows, and real-time monitoring.

## 🎯 Features

- **Buyer Chat**: Interface to the purchasing agent
- **Supplier Chat**: Interface to the supplier agent
- **Approvals Dashboard**: View and approve pending purchase orders
- **Activity Log**: Real-time trace of A2A and NPL activity
- **Metrics Dashboard**: Latency percentiles and call counters
- **Dark/Light Theme**: Toggle between themes

## 🏗️ Architecture

```
frontend/
├── src/
│   ├── App.tsx              # Main app with tab navigation
│   ├── components/
│   │   ├── BuyerChat.tsx    # Buyer agent chat interface
│   │   ├── SupplierChat.tsx # Supplier agent chat interface
│   │   ├── ApprovalDashboard.tsx  # Pending approvals
│   │   ├── ActivityLog.tsx  # Real-time activity feed
│   │   └── MetricsDashboard.tsx   # Performance metrics
│   ├── contexts/
│   │   └── ThemeContext.tsx # Dark/light mode state
│   ├── clients/
│   │   └── commerce/        # Auto-generated NPL API types
│   └── hooks/
│       └── usePendingApprovals.ts
├── openapi/
│   └── commerce-openapi.json  # NPL Engine OpenAPI spec
└── dist/                      # Production build
```

## 🚀 Development Setup

### Prerequisites
- Node.js 18+
- NPL Engine running on http://localhost:12000
- Chat API running on http://localhost:8001
- Activity API running on http://localhost:8002

### Install & Run

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

Open http://localhost:5173

### Production Build

```bash
npm run build
```

Build output is in `dist/`.

## 🔄 Regenerating Types

When NPL protocols change, regenerate TypeScript types:

```bash
# Download latest OpenAPI spec
curl -s http://localhost:12000/npl/commerce/-/openapi.json > openapi/commerce-openapi.json

# Regenerate TypeScript types
npx openapi-typescript openapi/commerce-openapi.json -o ./src/clients/commerce/types.ts
```

## 📡 API Endpoints

| Service | Port | Purpose |
|---------|------|---------|
| NPL Engine | 12000 | Protocol state, actions |
| Keycloak | 11000 | Authentication |
| Chat API | 8001 | Agent chat interface |
| Activity API | 8002 | Activity logs & metrics |

## 🎨 Theming

The app supports dark and light themes via `ThemeContext`:

```tsx
import { useTheme } from './contexts/ThemeContext';

function MyComponent() {
  const { theme, toggleTheme } = useTheme();
  return <button onClick={toggleTheme}>{theme}</button>;
}
```

## 📋 Component Details

### BuyerChat / SupplierChat
- Server-Sent Events (SSE) for streaming responses
- Agent "thinking" state displayed in gray
- Tool call indicators

### ApprovalDashboard
- Polls for pending approvals
- Notification badge when approvals waiting
- Approve button calls NPL Engine directly

### ActivityLog
- Real-time feed of all system activity
- Expandable A2A message details
- Color-coded by event type (NPL, A2A, LLM)
- Filter toggles for event types

### MetricsDashboard
- NPL Engine call counters
- A2A message counts
- LLM API call tracking
- Latency percentiles (P50, P95, P99)

## License

MIT License
