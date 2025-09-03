import { Routes, Route } from 'react-router-dom'
import RobotControl from './pages/RobotControl'

function App() {
  return (
    <Routes>
      <Route path="/" element={<RobotControl />} />
    </Routes>
  )
}

export default App
