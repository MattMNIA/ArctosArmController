import { Routes, Route } from 'react-router-dom'
import RobotControl from './pages/RobotControl'
import MotorStatus from './pages/MotorStatus'

function App() {
  return (
    <Routes>
      <Route path="/" element={<RobotControl />} />
      <Route path="/status" element={<MotorStatus />} />
    </Routes>
  )
}

export default App
