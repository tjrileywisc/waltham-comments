import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import "./styles.css";

import Videos from "./Videos";
import Search from "./Search"
import Navbar from "./Navbar";

const root = createRoot(document.getElementById("root"));
root.render(
  <StrictMode>
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<Search />} />
        <Route path="/videos" element={<Videos />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
);
