// src/pages/RobotControl.tsx
import { useState, useEffect } from "react";
import io from "socket.io-client";

const socket = io("http://localhost:5000");

export default function RobotControl() {
  const [msg, setMsg] = useState("Connecting...");
  const [joints, setJoints] = useState<number[]>([0,0,0,0,0,0]);

  useEffect(() => {
    socket.on("connect", () => setMsg("Connected to backend"));
    socket.on("status", (data: any) => setMsg(data.msg));
    return () => {
      socket.off("connect");
      socket.off("status");
    };
  }, []);

  const sendIK = async () => {
    const res = await fetch("http://localhost:5000/api/ik/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pose: { position: [0.3, 0.1, 0.2], orientation: [0,0,0,1] }, seed: joints.map((j: number) => j * Math.PI / 180) })
    });
    const data = await res.json();
    setJoints((data.joints as number[]).map((j: number) => j * 180 / Math.PI));
  };

  const executeMove = async () => {
    await fetch("http://localhost:5000/api/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q: joints.map((j: number) => j * Math.PI / 180) })
    });
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-bold">Robotic Arm Control</h1>
      <p>Status: {msg}</p>
      <div>
        <h2 className="font-semibold">Joints</h2>
        {joints.map((joint, index) => (
          <div key={index} className="flex items-center gap-2">
            <label>Joint {index + 1} (degrees):</label>
            <input
              type="number"
              step="0.01"
              value={joint}
              onChange={(e) => {
                const newJoints = [...joints];
                newJoints[index] = parseFloat(e.target.value) || 0;
                setJoints(newJoints);
              }}
              className="border p-1"
            />
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <button className="px-4 py-2 bg-blue-500 text-white rounded" onClick={sendIK}>
          Solve IK
        </button>
        <button className="px-4 py-2 bg-green-500 text-white rounded" onClick={executeMove}>
          Execute
        </button>
      </div>
    </div>
  );
}
