import React from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { TrendingUp, BarChart2, PieChart as PieIcon, Activity } from 'lucide-react';

const COLORS = [
  '#00c6ff', // Cyan
  '#ff5e62', // Coral
  '#00f260', // Green
  '#7f00ff', // Purple
  '#f59e0b', // Amber
  '#e11d48', // Rose
  '#3b82f6', // Blue
  '#10b981', // Emerald
];

export default function TrendChart({ payload, language }) {
  if (!payload || !payload.data || payload.data.length === 0) {
    return (
      <div className="placeholder-view">
        <Activity size={40} className="placeholder-icon" />
        <h3>{language === 'kn' ? 'ಯಾವುದೇ ವಿಶ್ಲೇಷಣೆ ಲಭ್ಯವಿಲ್ಲ' : 'No Trend Data Available'}</h3>
        <p>
          {language === 'kn'
            ? 'ಅಪರಾಧ ದಾಖಲೆಗಳ ಮಾಸಿಕ ಪ್ರವೃತ್ತಿ ಅಥವಾ ಜಿಲ್ಲಾವಾರು ಹೋಲಿಕೆಯನ್ನು ಪಡೆಯಲು ಪ್ರಶ್ನೆಯನ್ನು ಕೇಳಿ.'
            : 'Ask a question such as "Show monthly crime trends" or "What is the crime distribution in districts?" to see visualizations.'}
        </p>
      </div>
    );
  }

  const { group_by, data } = payload;

  // Custom Glassmorphic Tooltip
  const CustomTooltip = ({ active, payload: tPayload }) => {
    if (active && tPayload && tPayload.length) {
      return (
        <div style={{
          background: 'rgba(10, 14, 23, 0.9)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          backdropFilter: 'blur(8px)',
          borderRadius: '8px',
          padding: '10px 14px',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)'
        }}>
          <p style={{ margin: 0, fontSize: '12px', fontWeight: 'bold', color: '#ffffff' }}>
            {tPayload[0].name || tPayload[0].payload.key}
          </p>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--accent-cyan)', fontWeight: '600' }}>
            {language === 'kn' ? 'ಪ್ರಕರಣಗಳು' : 'Cases'}: {tPayload[0].value}
          </p>
        </div>
      );
    }
    return null;
  };

  const getChartTitle = () => {
    if (group_by === 'district') {
      return {
        title: language === 'kn' ? 'ಜಿಲ್ಲಾವಾರು ಪ್ರಕರಣಗಳ ಹಂಚಿಕೆ' : 'Crime Cases by District',
        icon: <BarChart2 size={16} className="header-logo" />
      };
    } else if (group_by === 'crime_type') {
      return {
        title: language === 'kn' ? 'ಅಪರಾಧದ ವಿಧಗಳ ವರ್ಗೀಕರಣ' : 'Cases by Crime Type',
        icon: <PieIcon size={16} className="header-logo" />
      };
    } else {
      return {
        title: language === 'kn' ? 'ತಿಂಗಳವಾರು ಅಪರಾಧ ಪ್ರವೃತ್ತಿ' : 'Monthly Crime Timeline',
        icon: <TrendingUp size={16} className="header-logo" />
      };
    }
  };

  const { title, icon } = getChartTitle();

  return (
    <div className="trend-chart-container">
      <div className="chart-header-row">
        <div className="chart-title">
          {icon}
          <span>{title}</span>
        </div>
      </div>

      <div className="chart-wrapper">
        <ResponsiveContainer width="100%" height="100%">
          {group_by === 'district' ? (
            <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="key" angle={-45} textAnchor="end" height={60} />
              <YAxis allowDecimals={false} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="count" name={language === 'kn' ? 'ಪ್ರಕರಣಗಳ ಸಂಖ್ಯೆ' : 'Case Count'} radius={[4, 4, 0, 0]}>
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          ) : group_by === 'crime_type' ? (
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="45%"
                labelLine={false}
                label={({ key, percent }) => `${key}: ${(percent * 100).toFixed(0)}%`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="count"
                nameKey="key"
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
              <Legend verticalAlign="bottom" height={36} iconType="circle" />
            </PieChart>
          ) : (
            <LineChart data={data} margin={{ top: 10, right: 20, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="key" />
              <YAxis allowDecimals={false} />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="count"
                name={language === 'kn' ? 'ಪ್ರಕರಣಗಳು' : 'Cases'}
                stroke="var(--accent-cyan)"
                strokeWidth={3}
                activeDot={{ r: 6 }}
                dot={{ stroke: 'var(--accent-cyan)', strokeWidth: 2, r: 4, fill: '#0a0e17' }}
              />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
