import React from "react";
import ChatWidget from "../components/ChatWidget";

// Root wraps every page in Docusaurus — ChatWidget appears site-wide
export default function Root({ children }) {
  return (
    <>
      {children}
      <ChatWidget />
    </>
  );
}
