import React from 'react';
import { Layout, Card, Typography, Space } from 'antd';
import Header from './components/Header';
import HeaderComparison from './components/HeaderComparison';
import 'antd/dist/reset.css';
import './App.css';

const { Content } = Layout;
const { Title, Paragraph } = Typography;

function App() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header />
      
      <Content style={{ marginTop: '56px', padding: '24px', backgroundColor: '#f0f2f5' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <Title level={2}>Dashboard Principal</Title>
          
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <HeaderComparison />
            
            <Card>
              <Title level={4}>Header Otimizado</Title>
              <Paragraph>
                O header foi completamente refatorado para ser mais compacto e eficiente:
              </Paragraph>
              <ul>
                <li>Altura reduzida para apenas 56px</li>
                <li>Layout horizontal com alinhamento perfeito</li>
                <li>Barra de pesquisa elegante à esquerda</li>
                <li>Ícones e avatar organizados à direita</li>
                <li>Design responsivo para diferentes tamanhos de tela</li>
              </ul>
            </Card>

            <Card>
              <Title level={4}>Melhorias Implementadas</Title>
              <Paragraph>
                As seguintes otimizações foram aplicadas:
              </Paragraph>
              <ul>
                <li><strong>Redução de altura:</strong> De um header excessivamente grande para apenas 56px</li>
                <li><strong>Alinhamento horizontal:</strong> Todos os elementos em uma única linha</li>
                <li><strong>Espaçamento otimizado:</strong> Uso do componente Space do Ant Design</li>
                <li><strong>Ícones menores:</strong> Tamanho reduzido para 18px</li>
                <li><strong>Avatar compacto:</strong> Tamanho de 32px para economia de espaço</li>
                <li><strong>Responsividade:</strong> Adaptação automática para dispositivos móveis</li>
              </ul>
            </Card>

            <Card>
              <Title level={4}>Benefícios</Title>
              <Paragraph>
                O novo design do header proporciona:
              </Paragraph>
              <ul>
                <li>Mais espaço para o conteúdo principal</li>
                <li>Interface mais limpa e profissional</li>
                <li>Melhor experiência do usuário</li>
                <li>Navegação mais intuitiva</li>
                <li>Visual moderno e minimalista</li>
              </ul>
            </Card>
          </Space>
        </div>
      </Content>
    </Layout>
  );
}

export default App;
