
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import "./styles.css";

import App from "./App";
import Search from "./Search"
import Navbar from "./Navbar";

const root = createRoot(document.getElementById("root"));
root.render(
  <StrictMode>
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/search" element={<Search />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
);