# RSCE: Deployment & Demo Walkthrough Recording Guide

This guide outlines the steps to deploy the Research Synthesis & Contradiction Engine (RSCE) to the cloud and record a professional portfolio walkthrough video/GIF.

---

## 🚀 1. Deploy the Backend to Fly.io

The backend runs as a FastAPI service inside a Docker container. Fly.io is an excellent platform for hosting this container.

### Step 1: Install Flyctl
If you don't have the Fly CLI installed, run:
- **macOS/Linux**: `curl -L https://fly.io/install.sh | sh`
- **Windows (PowerShell)**: `iwr https://fly.io/install.ps1 -useb | iex`

### Step 2: Launch the App
Run the setup command from the project root (where the `Dockerfile` resides):
```bash
fly launch
```
- Select your app name (e.g., `rsce-backend`).
- Choose your preferred deployment region.
- When prompted to set up a database, select **No** (the SQLite database is created inside the persistent volume or as a local temp file; for portfolio staging, standard local disk writes are sufficient).
- When prompted to deploy now, select **No** (we need to configure secrets first).

### Step 3: Configure Environment Secrets
The backend requires your LLM API keys. Run:
```bash
fly secrets set GEMINI_API_KEY="your_actual_gemini_api_key"
fly secrets set PUBMED_EMAIL="your_email@example.com"
```

### Step 4: Deploy the Backend
Deploy the container with:
```bash
fly deploy
```
Once completed, your API will be live at `https://<your-app-name>.fly.dev/docs`. Copy this URL to update the backend API endpoint URL in the frontend configurations.

---

## 🎨 2. Deploy the Frontend to Vercel

The Next.js frontend can be hosted for free on **Vercel** with one-click integration.

### Step 1: Push Project to GitHub
Initialize your git repository (if not already done) and push the code:
```bash
git init
git add .
git commit -m "Initial commit"
# Link to your GitHub repo and push
git remote add origin https://github.com/your-username/rsce.git
git branch -M main
git push -u origin main
```

### Step 2: Import to Vercel
1. Log in to [Vercel](https://vercel.com).
2. Click **Add New** > **Project** and import your `rsce` repository.
3. Configure the project:
   - **Framework Preset**: Next.js
   - **Root Directory**: `frontend`
   - **Environment Variables**: Add `NEXT_PUBLIC_API_URL` pointing to your Fly.io backend URL:
     ```env
     NEXT_PUBLIC_API_URL=https://rsce-backend.fly.dev
     ```
4. Click **Deploy**. Vercel will build and serve your frontend.

---

## 📹 3. Record a Walkthrough Video/GIF

A 30-second visual demonstration is the single most effective "portfolio power move" to get recruiter attention.

### Recording Tools
- **Loom** / **Vimeo Record** (Browser extensions, very fast)
- **Screenity** (Free, open-source browser extension with annotations)
- **OBS Studio** (For high-quality local recording)

### Recommended Walkthrough Script (30 Seconds)
1. **Search UI (0–8s)**: Start on the Next.js landing page. Type a query like `"Does metformin reduce cancer risk?"` and hit enter. Show the WebSocket-driven progress bar fetching papers and extracting claims in real time.
2. **Interactive Graph (8–20s)**: Switch to the results page. Hover over a few nodes, click a claim node, and show the claim details, polarity, population, and citation details appearing in the sidebar. Show the color-coded supports/contradicts edges.
3. **Narrative Synthesis (20–30s)**: Scroll through the RAG-generated consensus narrative, showing the structured clinical contradictions table and key methodological differences.

### Convert Video to GIF (for GitHub README)
If you want to display the walkthrough directly in your GitHub README, convert the video into a high-quality GIF:
- Use [Ezgif](https://ezgif.com/) or run `ffmpeg` locally:
  ```bash
  ffmpeg -i walkthrough.mp4 -vf "fps=10,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 docs/walkthrough.gif
  ```
- Reference it in your `README.md` under the title:
  ```markdown
  ![Walkthrough Tour](docs/walkthrough.gif)
  ```
