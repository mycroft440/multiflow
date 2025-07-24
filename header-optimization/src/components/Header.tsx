import React from 'react';
import { Layout, Input, Space, Badge, Avatar, Row, Col } from 'antd';
import { 
  SearchOutlined, 
  BellOutlined, 
  QuestionCircleOutlined,
  UserOutlined 
} from '@ant-design/icons';
import './Header.css';

const { Header: AntHeader } = Layout;

const Header: React.FC = () => {
  return (
    <AntHeader className="app-header">
      <Row justify="space-between" align="middle" style={{ height: '100%' }}>
        {/* Barra de pesquisa - lado esquerdo */}
        <Col xs={14} sm={16} md={12} lg={10}>
          <Input.Search
            placeholder="Pesquisar..."
            prefix={<SearchOutlined />}
            allowClear
            size="middle"
            style={{ maxWidth: '400px', width: '100%' }}
            onSearch={(value) => console.log('Pesquisando:', value)}
          />
        </Col>

        {/* Ícones e avatar do usuário - lado direito */}
        <Col>
          <Space size="middle" align="center">
            {/* Ícone de notificações */}
            <Badge count={3} size="small">
              <BellOutlined 
                style={{ fontSize: '18px', cursor: 'pointer' }}
                onClick={() => console.log('Notificações clicadas')}
              />
            </Badge>

            {/* Ícone de ajuda */}
            <QuestionCircleOutlined 
              style={{ fontSize: '18px', cursor: 'pointer' }}
              onClick={() => console.log('Ajuda clicada')}
            />

            {/* Avatar do usuário */}
            <Avatar 
              size={32} 
              icon={<UserOutlined />}
              style={{ cursor: 'pointer', backgroundColor: '#1890ff' }}
              onClick={() => console.log('Perfil do usuário clicado')}
            />
          </Space>
        </Col>
      </Row>
    </AntHeader>
  );
};

export default Header;