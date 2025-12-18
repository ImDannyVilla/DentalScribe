# Scribe32 - AI Medical Scribe

AI-powered clinical documentation for dental practices.

##  Features
- Real-time audio transcription (Deepgram)
- AI-generated SOAP notes (AWS Bedrock/Claude)
- Patient management
- Custom note templates
- Team management with role-based access

##  Architecture
- **Frontend:** Vanilla JS + Vite
- **Backend:** AWS SAM (Lambda, API Gateway, DynamoDB)
- **Auth:** AWS Cognito
- **AI:** AWS Bedrock (Claude), Deepgram

## Demo


##  Setup

### Prerequisites
- AWS Account
- Node.js 18+
- AWS SAM CLI

### Backend Setup
```bash
cd backend
cp samconfig.example.toml samconfig.toml
# Edit samconfig.toml with your values
sam build
sam deploy
```

### Frontend Setup
```bash
cd web-app
cp src/config.example.js src/config.js
# Edit config.js with your API endpoints
npm install
npm run dev
```

##  License
MIT
