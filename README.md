# BlindSight AI

Real-time visual accessibility assistant powered by Vision Agents SDK and OpenAI GPT-4o Realtime.

2.2 billion people worldwide live with vision impairment. BlindSight AI turns any smartphone camera into a real-time visual guide — narrating scenes, reading text, and warning about hazards in natural spoken voice.

## Features

- Real-time scene narration via GPT-4o Realtime
- Proactive hazard detection — steps, obstacles, moving objects
- Text reading — signs, menus, labels, screens
- Voice command support — "what do you see?", "read this", "any hazards?"
- Sub-500ms latency via Stream edge network
- Mobile-first, works on iPhone Safari with no app install required

## Tech Stack

- Vision Agents SDK by Stream
- OpenAI GPT-4o Realtime API
- Next.js 15 + Chakra UI v2
- Stream Video WebRTC
- Heroku (Python agent) + Vercel (frontend)

## Project structure

```
visonagentforblinds/
├── blindsight-backend/    Python AI agent (deploys to Heroku)
│   ├── main.py
│   ├── Procfile
│   ├── runtime.txt
│   ├── requirements.txt
│   └── .env.example
├── blindsight-frontend/   Next.js web app (deploys to Vercel)
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── providers.tsx
│   │   └── api/token/route.ts
│   ├── components/
│   │   ├── LandingScreen.tsx
│   │   ├── ActiveCallScreen.tsx
│   │   └── CameraView.tsx
│   └── .env.local.example
└── DEPLOYMENT.md          Full deployment instructions
```

## Quick start — see DEPLOYMENT.md for the full guide

### Backend (Heroku)
```bash
cd blindsight-backend
cp .env.example .env   # add your keys
heroku create && git push heroku main
heroku ps:scale worker=1
```

### Frontend (Vercel)
```bash
cd blindsight-frontend
cp .env.local.example .env.local   # add your keys
npm run dev                         # local dev
vercel --prod                       # deploy to production
```

## Demo script (60 seconds)

1. Open the Vercel URL on iPhone Safari, tap Start Session (0-8s)
2. Agent greets and immediately describes the room (8-18s)
3. Walk toward a chair — agent warns about the obstacle (18-28s)
4. Hold up a book cover — agent reads the text aloud (28-40s)
5. Say "what do you see?" — agent gives a scene summary (40-52s)
6. End title: "BlindSight AI — real-time vision for everyone." (52-60s)
