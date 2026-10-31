import React from 'react';
import { createRoot } from 'react-dom/client';
import '../css/styles.css';
import App from './App.jsx';
import AuthGate from './AuthGate.jsx';

const rootElement = document.getElementById('root');
if (rootElement) {
  createRoot(rootElement).render(React.createElement(AuthGate, null, React.createElement(App)));
}
