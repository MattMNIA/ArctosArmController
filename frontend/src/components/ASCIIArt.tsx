import React from 'react';

const FerbASCIIArt: React.FC = () => {
  const asciiArt = `
 ███████╗███████╗██████╗ ██████╗
 ██╔════╝██╔════╝██╔══██╗██╔══██╗
 █████╗  █████╗  ██████╔╝██████╔╝
 ██╔══╝  ██╔══╝  ██╔══██╗██╔══██╗
 ██║     ███████╗██║  ██║██████╔╝
 ╚═╝     ╚══════╝╚═╝  ╚═╝╚═════╝
`;

  return (
    <pre className="text-green-400 font-mono text-xs leading-tight">
      {asciiArt}
    </pre>
  );
};

export default FerbASCIIArt;