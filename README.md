# Mnenja-_1

## Frontend

Uporabniški vmesnik je prepisan v modularno Vue 3 (TypeScript) aplikacijo v mapi [`frontend/`](frontend/). Za razvoj uporabite Vite:

```bash
cd frontend
npm install
npm run dev
```

Za produkcijski build uporabite `npm run build`, statične datoteke se shranijo v `frontend/dist`. FastAPI aplikacija samodejno postreže `index.html` in `/assets` iz te mape, če je build prisoten.