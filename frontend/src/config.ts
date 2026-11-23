// GitHub Pages serves the interface only. No fabricated connection or capture data.
export const staticHosting = (import.meta as ImportMeta & {env:Record<string,string>}).env.MODE === 'pages';
