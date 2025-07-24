import React from 'react';
import { Card, Row, Col, Typography } from 'antd';
import './HeaderComparison.css';

const { Title, Text } = Typography;

const HeaderComparison: React.FC = () => {
  return (
    <div className="header-comparison">
      <Title level={3} style={{ textAlign: 'center', marginBottom: 32 }}>
        Comparação: Antes vs Depois
      </Title>
      
      <Row gutter={[24, 24]}>
        {/* Header Antigo - Problemático */}
        <Col xs={24} lg={12}>
          <Card 
            title="❌ Header Antigo - Problemático" 
            className="comparison-card"
            headStyle={{ backgroundColor: '#fff1f0', borderBottom: '1px solid #ffccc7' }}
          >
            <div className="old-header-demo">
              <div className="old-header">
                <div className="old-header-content">
                  <div className="old-search-section">
                    <input className="old-search" placeholder="Pesquisar..." />
                  </div>
                  <div className="old-icons-section">
                    <div className="old-icon">🔔</div>
                    <div className="old-icon">❓</div>
                    <div className="old-user-icon">👤</div>
                  </div>
                </div>
              </div>
              
              <div className="issues-list">
                <Text type="danger">Problemas identificados:</Text>
                <ul>
                  <li>Altura excessiva (120px+)</li>
                  <li>Muito espaço desperdiçado</li>
                  <li>Elementos desalinhados</li>
                  <li>Padding desnecessário</li>
                  <li>Visual desorganizado</li>
                </ul>
              </div>
            </div>
          </Card>
        </Col>

        {/* Header Novo - Otimizado */}
        <Col xs={24} lg={12}>
          <Card 
            title="✅ Header Novo - Otimizado" 
            className="comparison-card"
            headStyle={{ backgroundColor: '#f0f9ff', borderBottom: '1px solid '#e6f7ff' }}
          >
            <div className="new-header-demo">
              <div className="new-header">
                <div className="new-header-content">
                  <div className="new-search-section">
                    <input className="new-search" placeholder="Pesquisar..." />
                  </div>
                  <div className="new-icons-section">
                    <span className="new-icon">🔔</span>
                    <span className="new-icon">❓</span>
                    <span className="new-avatar">👤</span>
                  </div>
                </div>
              </div>
              
              <div className="improvements-list">
                <Text type="success">Melhorias aplicadas:</Text>
                <ul>
                  <li>Altura compacta (56px)</li>
                  <li>Layout eficiente</li>
                  <li>Alinhamento perfeito</li>
                  <li>Espaçamento otimizado</li>
                  <li>Visual profissional</li>
                </ul>
              </div>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default HeaderComparison;