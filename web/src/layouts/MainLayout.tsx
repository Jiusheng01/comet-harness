import { Avatar, Badge, Button, Drawer, Dropdown, Input, Layout, Menu, message } from 'antd'
import {
  AppstoreOutlined,
  BellOutlined,
  BookOutlined,
  ClockCircleOutlined,
  CommentOutlined,
  DownOutlined,
  FileSearchOutlined,
  HddOutlined,
  HistoryOutlined,
  LogoutOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  RobotOutlined,
  RocketOutlined,
  SearchOutlined,
  SettingOutlined,
  ShareAltOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useChatHeaderStore } from '@/stores/chatHeaderStore'
import { agentTaskApi } from '@/api/agentTask'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'

const { Sider, Content, Header } = Layout

const menuItems = [
  {
    type: 'group' as const,
    label: '工作台',
    children: [{ key: '/', icon: <AppstoreOutlined />, label: '仪表盘' }],
  },
  {
    type: 'group' as const,
    label: '工作负载',
    children: [
      { key: '/chat', icon: <CommentOutlined />, label: '对话' },
      { key: '/research', icon: <FileSearchOutlined />, label: '深度研究' },
      { key: '/agent-tasks', icon: <ClockCircleOutlined />, label: '定时任务' },
    ],
  },
  {
    type: 'group' as const,
    label: '运行',
    children: [{ key: '/traces', icon: <HistoryOutlined />, label: '执行记录' }],
  },
  {
    type: 'group' as const,
    label: '知识与上下文',
    children: [
      { key: '/knowledge', icon: <BookOutlined />, label: '知识库' },
      { key: '/memory', icon: <HddOutlined />, label: '记忆' },
    ],
  },
  {
    type: 'group' as const,
    label: '配置',
    children: [
      { key: '/settings/agent', icon: <RobotOutlined />, label: 'Agent 配置' },
      { key: '/settings/models', icon: <SettingOutlined />, label: '模型配置' },
      { key: '/settings/skills', icon: <ThunderboltOutlined />, label: 'Skills' },
      { key: '/settings/tools', icon: <ToolOutlined />, label: '工具配置' },
    ],
  },
]

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 768,
  )

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const handler = (event: MediaQueryListEvent) => setIsMobile(event.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return isMobile
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const isMobile = useIsMobile()
  const isHome = location.pathname === '/'

  const chatHeaderActive = useChatHeaderStore((state) => state.active)
  const chatOpenHistory = useChatHeaderStore((state) => state.openHistory)
  const chatNewChat = useChatHeaderStore((state) => state.newChat)
  const chatOpenShare = useChatHeaderStore((state) => state.openShare)
  const chatCanShare = useChatHeaderStore((state) => state.canShare)
  const showChatHeader = isMobile && chatHeaderActive && location.pathname === '/chat'

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [unreadTasks, setUnreadTasks] = useState(0)

  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  useEffect(() => {
    let alive = true
    const fetchUnread = () => {
      agentTaskApi
        .unreadCount()
        .then(({ data }) => {
          if (alive) setUnreadTasks(data.count)
        })
        .catch(() => {})
    }
    fetchUnread()
    const timer = window.setInterval(fetchUnread, 60000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [location.pathname])

  useEffect(() => {
    const root = document.documentElement
    root.classList.add('app-shell-active')
    return () => root.classList.remove('app-shell-active')
  }, [])

  const onLogout = async () => {
    await logout()
    message.success('已退出登录')
    navigate('/login', { replace: true })
  }

  const profileMenu = {
    items: [
      {
        key: 'profile',
        icon: <UserOutlined />,
        label: '个人中心',
        onClick: () => navigate('/profile'),
      },
      { type: 'divider' as const },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: '退出登录',
        onClick: onLogout,
      },
    ],
  }

  const brand = (
    <div
      style={{
        height: 64,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        paddingInline: 20,
        color: '#232536',
      }}
    >
      <span
        style={{
          width: 30,
          height: 30,
          borderRadius: 10,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#6256d9',
          background: 'linear-gradient(135deg, #f0edff, #e9efff)',
          fontSize: 17,
          flexShrink: 0,
        }}
      >
        <RocketOutlined />
      </span>
      <span style={{ fontWeight: 700, fontSize: 19, whiteSpace: 'nowrap' }}>Comet</span>
    </div>
  )

  const sidebarUser = (
    <Dropdown menu={profileMenu} placement="topLeft" trigger={['click']}>
      <button
        type="button"
        style={{
          width: 'calc(100% - 24px)',
          minHeight: 52,
          margin: '10px 12px 12px',
          padding: '8px 10px',
          border: 0,
          borderRadius: 11,
          background: 'transparent',
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          textAlign: 'left',
          cursor: 'pointer',
        }}
      >
        {user?.avatar ? (
          <AuthenticatedImage
            src={user.avatar}
            alt="头像"
            style={{
              width: 30,
              height: 30,
              borderRadius: '50%',
              objectFit: 'cover',
              display: 'block',
              flexShrink: 0,
            }}
          />
        ) : (
          <Avatar size={30} style={{ background: '#5b57c8', flexShrink: 0 }}>
            {user?.username?.[0]?.toUpperCase() ?? <UserOutlined />}
          </Avatar>
        )}
        <span
          style={{
            minWidth: 0,
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            color: '#444657',
            fontSize: 13,
          }}
        >
          {user?.email || user?.nickname || user?.username || '用户'}
        </span>
        <DownOutlined style={{ color: '#a2a5b4', fontSize: 10 }} />
      </button>
    </Dropdown>
  )

  const navMenu = () => {
    const items = menuItems.map((group) => ({
      ...group,
      children: group.children.map((item) =>
        item.key === '/agent-tasks' && unreadTasks > 0
          ? {
              ...item,
              label: (
                <Badge count={unreadTasks} size="small" offset={[10, 0]}>
                  <span>{item.label}</span>
                </Badge>
              ),
            }
          : item,
      ),
    }))

    return (
      <Menu
        mode="inline"
        theme="light"
        selectedKeys={[location.pathname]}
        items={items}
        onClick={({ key }) => navigate(key)}
        style={{ borderInlineEnd: 'none', background: 'transparent' }}
      />
    )
  }

  const sidebarBody = (
    <>
      {brand}
      <div className="app-shell-sider-menu" style={{ paddingBottom: 4 }}>
        {navMenu()}
      </div>
      <div style={{ flexShrink: 0, borderTop: '1px solid #f2f3f5' }}>{sidebarUser}</div>
    </>
  )

  return (
    <Layout style={{ height: '100%', overflow: 'hidden' }} className="app-shell">
      {!isMobile && (
        <Sider
          width={260}
          style={{
            borderInlineEnd: '1px solid #f0f0f0',
            background: '#fff',
          }}
        >
          {sidebarBody}
        </Sider>
      )}

      {isMobile && (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={260}
          closable={false}
          styles={{
            body: {
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
              height: '100%',
            },
          }}
        >
          {sidebarBody}
        </Drawer>
      )}

      <Layout className="app-shell-main" style={{ background: '#fafafa' }}>
        <Header
          style={{
            flexShrink: 0,
            height: 64,
            paddingInline: isMobile ? 12 : 20,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            borderBottom: '1px solid #f0f0f0',
            background: '#fff',
          }}
        >
          {isMobile && (
            <Button
              type="text"
              aria-label="菜单"
              icon={<MenuUnfoldOutlined />}
              onClick={() => setDrawerOpen(true)}
              style={{ flexShrink: 0, fontSize: 18 }}
            />
          )}

          {showChatHeader ? (
            <div
              style={{
                flex: 1,
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                gap: 8,
                minWidth: 0,
              }}
            >
              <Button type="text" icon={<HistoryOutlined />} onClick={() => chatOpenHistory?.()}>
                会话
              </Button>
              <Button type="text" icon={<PlusOutlined />} onClick={() => chatNewChat?.()}>
                新对话
              </Button>
              {chatCanShare && (
                <Button type="text" icon={<ShareAltOutlined />} onClick={() => chatOpenShare?.()}>
                  分享
                </Button>
              )}
            </div>
          ) : (
            <div
              style={{
                flex: 1,
                display: 'flex',
                justifyContent: 'flex-start',
                minWidth: 0,
              }}
            >
              <Input
                className="top-search"
                prefix={<SearchOutlined style={{ color: '#9da0af' }} />}
                placeholder={isMobile ? '搜索…' : '搜索知识、对话、记忆...'}
                allowClear
                style={{ width: '100%', maxWidth: 410 }}
                onPressEnter={(event) => {
                  const q = (event.target as HTMLInputElement).value.trim()
                  if (q) navigate(`/search?q=${encodeURIComponent(q)}`)
                }}
              />
            </div>
          )}

          <Badge count={unreadTasks} size="small" offset={[-2, 5]}>
            <Button
              type="text"
              aria-label="自动任务通知"
              icon={<BellOutlined />}
              onClick={() => navigate('/agent-tasks')}
              style={{ flexShrink: 0, color: '#505263' }}
            />
          </Badge>

          <Dropdown menu={profileMenu} placement="bottomRight">
            <button
              type="button"
              aria-label="用户菜单"
              style={{
                border: 0,
                padding: 0,
                background: 'transparent',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                flexShrink: 0,
              }}
            >
              {user?.avatar ? (
                <AuthenticatedImage
                  src={user.avatar}
                  alt="头像"
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    objectFit: 'cover',
                    display: 'block',
                  }}
                />
              ) : (
                <Avatar size={32} style={{ background: '#23314d' }}>
                  {user?.username?.[0]?.toUpperCase() ?? <UserOutlined />}
                </Avatar>
              )}
            </button>
          </Dropdown>
        </Header>

        <Content
          className={`app-shell-content${isHome ? ' app-shell-content--home' : ''}`}
          style={{
            padding: isMobile ? 14 : isHome ? 16 : 20,
            overflow: !isMobile && isHome ? 'hidden' : undefined,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
