import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';

interface Message {
  id: string;
  type: 'user' | 'agent';
  content: string;
  commands?: string[];
  riskLevel?: string;
  needsConfirmation?: boolean;
  originalInput?: string;
  confirmedAction?: 'executing' | 'confirmed' | 'cancelled';
  timestamp: Date;
  serverId?: string;
}

interface Capability {
  name: string;
  description: string;
  actions: string[];
}

interface Server {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_type: string;
  key_path: string;
  status: string;
  os_name: string;
  distro_name: string;
}

interface SystemInfo {
  os_name: string;
  distro_name: string;
  kernel: string;
  current_user: string;
  hostname: string;
}

type Language = 'zh' | 'en';

interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

const i18n = {
  zh: {
    title: 'OS Agent',
    welcome: '欢迎使用 OS Agent',
    welcomeDesc: '使用自然语言管理您的操作系统',
    enterCommand: '输入命令或问题...',
    send: '发送',
    capabilities: '可用能力',
    quickCommands: '快捷命令',
    disk: '💾 磁盘',
    process: '⚙️ 进程',
    memory: '📊 内存',
    network: '🌐 网络',
    user: '👤 用户',
    diskCmd: '查看磁盘使用情况',
    processCmd: '查看运行中的进程',
    memoryCmd: '查看内存使用情况',
    networkCmd: '查看网络配置',
    riskWarning: '风险警告',
    highRiskWarning: '高风险操作警告',
    cancel: '取消',
    confirm: '确认执行',
    checking: '思考中...',
    online: '在线',
    systemInfo: '系统信息',
    os: '操作系统',
    distro: '发行版',
    kernel: '内核版本',
    currentUser: '当前用户',
    hostname: '主机名',
    language: '语言',
    clearChat: '清空对话',
    voiceInput: '语音输入',
    voiceOutput: '语音播报',
    listening: '正在聆听...',
    voiceNotSupported: '浏览器不支持语音识别',
    serverManagement: '服务器管理',
    localServer: '本地服务器',
    remoteServer: '远程服务器',
    addServer: '添加服务器',
    connected: '已连接',
    disconnected: '未连接',
    connecting: '连接中...',
    connect: '连接',
    disconnect: '断开',
    retry: '重试',
    serverName: '服务器名称',
    serverHost: '主机地址',
    serverPort: 'SSH端口',
    serverUser: '用户名',
    authType: '认证方式',
    keyAuth: '密钥认证',
    passwordAuth: '密码认证',
    keyPath: '密钥路径',
    password: '密码',
    currentTarget: '当前目标',
    editServer: '编辑',
    deleteServer: '删除',
    save: '保存',
    sessionHistory: '对话历史',
    newSession: '新建会话',
    deleteSession: '删除会话',
    noHistory: '暂无历史会话',
    messagesCount: '条消息',
    defaultMessage: '默认会话',
    sudoTitle: '需要 sudo 权限',
    sudoDesc: '当前用户没有免密 sudo 权限，部分操作（如创建用户）需要 sudo 密码。',
    sudoPlaceholder: '请输入 sudo 密码...',
    sudoSubmit: '验证密码',
    sudoSkip: '跳过（部分功能受限）',
    sudoNoPermission: '当前用户没有 sudo 权限，无法执行管理操作',
    sudoOk: 'sudo 权限已验证',
  },
  en: {
    title: 'OS Agent',
    welcome: 'Welcome to OS Agent',
    welcomeDesc: 'Manage your OS with natural language',
    enterCommand: 'Enter command or question...',
    send: 'Send',
    capabilities: 'Capabilities',
    quickCommands: 'Quick Commands',
    disk: '💾 Disk',
    process: '⚙️ Process',
    memory: '📊 Memory',
    network: '🌐 Network',
    user: '👤 User',
    diskCmd: 'Check disk usage',
    processCmd: 'List running processes',
    memoryCmd: 'Check memory usage',
    networkCmd: 'Check network configuration',
    riskWarning: 'Risk Warning',
    highRiskWarning: 'High Risk Warning',
    cancel: 'Cancel',
    confirm: 'Confirm',
    checking: 'Thinking...',
    online: 'Online',
    systemInfo: 'System Info',
    os: 'OS',
    distro: 'Distribution',
    kernel: 'Kernel',
    currentUser: 'User',
    hostname: 'Hostname',
    language: 'Language',
    clearChat: 'Clear Chat',
    voiceInput: 'Voice Input',
    voiceOutput: 'Voice Output',
    listening: 'Listening...',
    voiceNotSupported: 'Speech recognition not supported',
    serverManagement: 'Server Management',
    localServer: 'Local Server',
    remoteServer: 'Remote Server',
    addServer: 'Add Server',
    connected: 'Connected',
    disconnected: 'Disconnected',
    connecting: 'Connecting...',
    connect: 'Connect',
    disconnect: 'Disconnect',
    retry: 'Retry',
    serverName: 'Server Name',
    serverHost: 'Host Address',
    serverPort: 'SSH Port',
    serverUser: 'Username',
    authType: 'Auth Type',
    keyAuth: 'Key Auth',
    passwordAuth: 'Password Auth',
    keyPath: 'Key Path',
    password: 'Password',
    currentTarget: 'Current Target',
    editServer: 'Edit',
    deleteServer: 'Delete',
    save: 'Save',
    sessionHistory: 'History',
    newSession: 'New Session',
    deleteSession: 'Delete Session',
    noHistory: 'No history yet',
    messagesCount: 'messages',
    defaultMessage: 'Default Session',
    sudoTitle: 'Sudo Required',
    sudoDesc: 'Your user does not have passwordless sudo. Some operations (e.g. create user) need sudo password.',
    sudoPlaceholder: 'Enter sudo password...',
    sudoSubmit: 'Verify Password',
    sudoSkip: 'Skip (some features limited)',
    sudoNoPermission: 'No sudo access. Cannot perform admin operations.',
    sudoOk: 'Sudo access verified',
  },
};

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [language, setLanguage] = useState<Language>('zh');
  const [isListening, setIsListening] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [servers, setServers] = useState<Server[]>([{
    id: 'local',
    name: '本地服务器',
    host: 'localhost',
    port: 22,
    username: '',
    auth_type: 'password',
    key_path: '',
    status: 'connected',
    os_name: '',
    distro_name: '',
  }]);
  const [currentServer, setCurrentServer] = useState<string>('local');
  const [showAddServer, setShowAddServer] = useState(false);
  const [editingServer, setEditingServer] = useState<Server | null>(null);
  const [editForm, setEditForm] = useState({
    name: '',
    host: '',
    port: 22,
    username: '',
    auth_type: 'password',
    key_path: '',
    password: '',
  });
  const [newServer, setNewServer] = useState({
    id: '',
    name: '',
    host: '',
    port: 22,
    username: '',
    auth_type: 'password',
    key_path: '',
    password: '',
  });
  const [systemInfo, setSystemInfo] = useState<SystemInfo>({
    os_name: '',
    distro_name: '',
    kernel: '',
    current_user: '',
    hostname: '',
  });
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>('default');
  const [showSudoModal, setShowSudoModal] = useState(false);
  const [sudoPassword, setSudoPassword] = useState('');
  const [sudoSubmitting, setSudoSubmitting] = useState(false);
  const [sudoStatus, setSudoStatus] = useState<{has_sudo: boolean; is_root: boolean; message: string} | null>(null);
  const pendingSudoCmdRef = useRef<string | null>(null);
  // 待确认的操作（确认后需要sudo密码时暂存）
  const pendingConfirmRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const t = i18n[language];

  const speechSupported = typeof AudioContext !== 'undefined' && navigator.mediaDevices !== undefined;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    fetchCapabilities();
    fetchSystemInfo();
    fetchServers();
    fetchSessions();
    checkSudo();
    // 加载默认会话的历史消息
    loadSessionMessages('default');
    // 自动检测 SSH 登录用户
    detectSshUser();
  }, []);

  useEffect(() => {
    if (currentServer === 'local') {
      fetchSystemInfo();
    } else {
      const server = servers.find(s => s.id === currentServer);
      if (server && server.status === 'connected') {
        setSystemInfo(prev => ({
          ...prev,
          os_name: server.os_name || prev.os_name,
          distro_name: server.distro_name || prev.distro_name,
          current_user: server.username || prev.current_user,
        }));
      }
    }
  }, [currentServer, servers]);

  const audioContextRef = useRef<AudioContext | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const audioSamplesRef = useRef<Float32Array[]>([]);

  const encodeWAV = (samples: Float32Array[], sampleRate: number): Blob => {
    const totalLength = samples.reduce((acc, s) => acc + s.length, 0);
    const merged = new Float32Array(totalLength);
    let offset = 0;
    for (const s of samples) {
      merged.set(s, offset);
      offset += s.length;
    }

    const buffer = new ArrayBuffer(44 + merged.length * 2);
    const view = new DataView(buffer);

    const writeString = (offset: number, str: string) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + merged.length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, merged.length * 2, true);

    for (let i = 0; i < merged.length; i++) {
      const s = Math.max(-1, Math.min(1, merged[i]));
      view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }

    return new Blob([buffer], { type: 'audio/wav' });
  };

  const toggleVoiceInput = () => {
    if (!speechSupported) {
      alert(t.voiceNotSupported);
      return;
    }

    if (isListening) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const stopRecording = () => {
    if (audioProcessorRef.current) {
      audioProcessorRef.current.disconnect();
      audioProcessorRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach(track => track.stop());
      audioStreamRef.current = null;
    }
    setIsListening(false);

    const samples = audioSamplesRef.current;
    audioSamplesRef.current = [];

    if (samples.length === 0) {
      console.log('无录音数据');
      return;
    }

    const wavBlob = encodeWAV(samples, 16000);
    console.log('WAV大小:', wavBlob.size, 'bytes');
    sendAudioForRecognition(wavBlob);
  };

  const sendAudioForRecognition = async (wavBlob: Blob) => {
    setInputValue('正在识别...');
    try {
      const formData = new FormData();
      formData.append('audio', wavBlob, 'recording.wav');

      const response = await fetch('/api/stt', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      console.log('STT响应:', data);

      if (data.success && data.text) {
        setInputValue(data.text);
      } else {
        setInputValue('');
        if (data.message && !data.success) {
          alert(data.message);
        } else if (!data.text) {
          console.log('未识别到语音内容');
        }
      }
    } catch (err) {
      console.error('语音识别请求失败:', err);
      setInputValue('');
      alert('语音识别服务不可用');
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        }
      });

      audioStreamRef.current = stream;
      audioSamplesRef.current = [];

      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      audioProcessorRef.current = processor;

      processor.onaudioprocess = (event) => {
        const channelData = event.inputBuffer.getChannelData(0);
        audioSamplesRef.current.push(new Float32Array(channelData));
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      setIsListening(true);
      console.log('录音已开始 (AudioContext, 16kHz PCM)');

    } catch (err: any) {
      console.error('获取麦克风失败:', err);
      if (err.name === 'NotAllowedError') {
        alert('请允许浏览器访问麦克风');
      } else if (err.name === 'NotFoundError') {
        alert('未检测到麦克风设备');
      } else {
        alert('无法启动录音: ' + err.message);
      }
    }
  };

  const speak = (text: string) => {
    if (!voiceEnabled) return;
    if (!('speechSynthesis' in window)) return;

    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language === 'zh' ? 'zh-CN' : 'en-US';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    speechSynthesis.speak(utterance);
  };

  const fetchCapabilities = async () => {
    try {
      const response = await fetch('/api/capabilities');
      const data = await response.json();
      setCapabilities(data.capabilities || []);
    } catch (error) {
      console.error('Failed to fetch capabilities:', error);
    }
  };

  const fetchSystemInfo = async () => {
    try {
      const response = await fetch('/api/system');
      const data = await response.json();
      setSystemInfo({
        os_name: data.os_name || '',
        distro_name: data.distro_name || '',
        kernel: data.kernel || '',
        current_user: data.current_user || '',
        hostname: data.hostname || '',
      });
    } catch (error) {
      console.error('Failed to fetch system info:', error);
    }
  };

  const fetchServers = async () => {
    try {
      const response = await fetch('/api/servers');
      const data = await response.json();
      if (data.servers && data.servers.length > 0) {
        setServers(data.servers);
      }
    } catch (error) {
      console.error('Failed to fetch servers:', error);
    }
  };

  // 自动检测 SSH 登录用户并切换身份
  const detectSshUser = async () => {
    try {
      const response = await fetch('/api/detect-ssh-user');
      const data = await response.json();
      if (data.success && data.ssh_user) {
        const sshUser = data.ssh_user;
        const shouldSwitch = window.confirm(
          `检测到你以 ${sshUser} 身份登录，是否以该用户身份执行命令？`
        );
        if (shouldSwitch) {
          try {
            const resp = await fetch('/api/servers/switch-user', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ username: sshUser }),
            });
            const result = await resp.json();
            if (result.success) {
              setSystemInfo(prev => ({ ...prev, current_user: sshUser }));
              // 添加一条系统消息
              setMessages(prev => [...prev, {
                id: Date.now().toString(),
                type: 'agent' as const,
                content: `已切换为 ${sshUser} 身份执行命令`,
                timestamp: new Date(),
              }]);
            } else {
              alert(`切换身份失败: ${result.message}`);
            }
          } catch (e) {
            console.error('切换用户失败:', e);
          }
        }
      }
    } catch (error) {
      // 检测失败不影响正常使用
      console.log('SSH 用户检测跳过:', error);
    }
  };

  const connectServer = async (server: Server) => {
    setServers(prev => prev.map(s => 
      s.id === server.id ? { ...s, status: 'connecting' } : s
    ));

    try {
      const response = await fetch('/api/servers/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: server.id,
          name: server.name,
          host: server.host,
          port: server.port,
          username: server.username,
          auth_type: server.auth_type,
          key_path: server.key_path || '',
          password: (server as any).password || '',
        }),
      });

      const data = await response.json();

      if (data.success) {
        setServers(prev => prev.map(s => 
          s.id === server.id 
            ? { 
                ...s, 
                status: 'connected',
                os_name: data.server_info?.os_name || '',
                distro_name: data.server_info?.distro_name || '',
              } 
            : s
        ));
        
        setCurrentServer(server.id);
        
        setSystemInfo(prev => ({
          ...prev,
          os_name: data.server_info?.os_name || '',
          distro_name: data.server_info?.distro_name || '',
          current_user: server.username || prev.current_user,
        }));
        
        alert(data.message || '连接成功');
      } else {
        setServers(prev => prev.map(s => 
          s.id === server.id ? { ...s, status: 'error' } : s
        ));
        alert(data.message || '连接失败');
      }
    } catch (error) {
      console.error('Connection error:', error);
      setServers(prev => prev.map(s => 
        s.id === server.id ? { ...s, status: 'error' } : s
      ));
      alert('连接失败：网络错误');
    }
  };

  const disconnectServer = async (server: Server) => {
    try {
      await fetch('/api/servers/disconnect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_id: server.id }),
      });
    } catch (e) {
      // ignore
    }

    setServers(prev => prev.map(s => 
      s.id === server.id ? { ...s, status: 'disconnected' as const, os_name: '', distro_name: '' } : s
    ));

    if (currentServer === server.id) {
      setCurrentServer('local');
    }
  };

  const deleteServer = (server: Server) => {
    if (server.id === 'local') return;
    if (!confirm(language === 'zh' ? `确定删除服务器 "${server.name}" 吗？` : `Delete server "${server.name}"?`)) return;

    setServers(prev => prev.filter(s => s.id !== server.id));

    if (currentServer === server.id) {
      setCurrentServer('local');
    }

    fetch('/api/servers/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ server_id: server.id }),
    }).catch(() => {});
  };

  const startEditServer = (server: Server) => {
    setEditingServer(server);
    setEditForm({
      name: server.name,
      host: server.host,
      port: server.port,
      username: server.username,
      auth_type: server.auth_type,
      key_path: server.key_path,
      password: (server as any).password || '',
    });
  };

  const saveEditServer = async () => {
    if (!editingServer) return;

    const updatedServer: Server = {
      ...editingServer,
      name: editForm.name,
      host: editForm.host,
      port: editForm.port,
      username: editForm.username,
      auth_type: editForm.auth_type,
      key_path: editForm.key_path,
      status: 'disconnected',
      os_name: '',
      distro_name: '',
    };

    setServers(prev => prev.map(s =>
      s.id === editingServer.id ? updatedServer : s
    ));

    setEditingServer(null);

    if (currentServer === editingServer.id) {
      setCurrentServer('local');
    }
  };

  const addNewServer = async () => {
    if (!newServer.host || !newServer.name) {
      alert('请填写服务器名称和地址');
      return;
    }

    const serverId = `remote-${Date.now()}`;
    const server: Server = {
      ...newServer,
      id: serverId,
      status: 'disconnected',
      os_name: '',
      distro_name: '',
    };

    setServers(prev => [...prev, server]);
    setShowAddServer(false);

    setNewServer({
      id: '',
      name: '',
      host: '',
      port: 22,
      username: '',
      auth_type: 'password',
      key_path: '',
      password: '',
    });

    await connectServer(server);
  };

  const checkSudo = async () => {
    try {
      const response = await fetch('/api/sudo/status');
      const data = await response.json();
      setSudoStatus(data);
    } catch (e) {
      // ignore
    }
  };

  // 检查消息是否因为 sudo 失败，如果是则弹出密码输入框
  const checkSudoNeeded = (msg: string) => {
    if (sudoStatus?.has_sudo || sudoStatus?.is_root) return false;
    // 匹配 sudo 权限/密码相关的错误
    const keywords = [
      'sudo: a password is required',
      'Permission denied',
      '权限不足',
      '需要 sudo 密码',
      '密码错误',
      '提示：请在页面',
      'Sorry, try again',
      'no password was provided',
      'incorrect password',
      '设置密码失败',
      '命令执行超时',
      '命令需要 sudo',
    ];
    return keywords.some(k => msg.includes(k));
  };

  const submitSudoPassword = async () => {
    if (!sudoPassword.trim() || sudoSubmitting) return;
    setSudoSubmitting(true);
    try {
      const response = await fetch('/api/sudo/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: sudoPassword }),
      });
      const data = await response.json();
      if (data.success) {
        setSudoStatus({ has_sudo: true, is_root: false, message: data.message });
        setShowSudoModal(false);
        setSudoPassword('');
        // 优先处理待确认的操作（确认后输密码的场景）
        const pendingConfirm = pendingConfirmRef.current;
        pendingConfirmRef.current = null;
        if (pendingConfirm) {
          await sendMessage(pendingConfirm, true);
          return;
        }
        // 备用：重发之前失败的命令
        const pendingCmd = pendingSudoCmdRef.current;
        pendingSudoCmdRef.current = null;
        if (pendingCmd) {
          await sendMessage(pendingCmd);
        }
      } else {
        alert(data.message || '密码错误');
      }
    } catch (e) {
      alert('验证失败');
    } finally {
      setSudoSubmitting(false);
    }
  };

  const fetchSessions = async () => {
    try {
      const response = await fetch('/api/sessions');
      const data = await response.json();
      if (data.success) {
        setSessions(data.sessions);
      }
    } catch (e) {
      // ignore
    }
  };

  const createNewSession = async () => {
    try {
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: t.newSession }),
      });
      const data = await response.json();
      if (data.success) {
        setSessions((prev) => [data.session, ...prev]);
        setCurrentSessionId(data.session.id);
        setMessages([]);
      }
    } catch (e) {
      console.error('创建会话失败:', e);
    }
  };

  const loadSessionMessages = async (sessionId: string) => {
    try {
      const response = await fetch(`/api/sessions/${sessionId}/messages`);
      const data = await response.json();
      if (data.success && data.messages.length > 0) {
        const loadedMessages: Message[] = [];
        for (const msg of data.messages) {
          loadedMessages.push({
            id: `u-${msg.id}`,
            type: 'user',
            content: msg.user_input,
            timestamp: new Date(msg.timestamp),
          });
          loadedMessages.push({
            id: `a-${msg.id}`,
            type: 'agent',
            content: msg.agent_response,
            commands: msg.commands,
            timestamp: new Date(msg.timestamp),
          });
        }
        setMessages(loadedMessages);
      }
    } catch (e) {
      console.error('加载会话消息失败:', e);
    }
  };

  const switchSession = async (sessionId: string) => {
    if (sessionId === currentSessionId) return;
    setCurrentSessionId(sessionId);
    setMessages([]);
    loadSessionMessages(sessionId);
  };

  const deleteSession = async (sessionId: string) => {
    if (!confirm(language === 'zh' ? '确定删除该会话吗？' : 'Delete this session?')) return;
    try {
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        setCurrentSessionId('default');
        setMessages([]);
      }
    } catch (e) {
      console.error('删除会话失败:', e);
    }
  };

  // 确认操作：先检查 sudo 状态，需要密码则弹框，否则直接执行
  const handleConfirm = async (message: string) => {
    // 如果 sudo 状态未知或需要密码但没设置，先弹密码框
    if (!sudoStatus?.has_sudo && !sudoStatus?.is_root) {
      // 刷新 sudo 状态
      try {
        const resp = await fetch('/api/sudo/status');
        const status = await resp.json();
        setSudoStatus(status);
        if (!status.has_sudo && !status.is_root) {
          // 需要密码，暂存操作，弹密码框
          pendingConfirmRef.current = message;
          setShowSudoModal(true);
          return;
        }
      } catch (e) {
        // 无法检查 sudo，直接执行
      }
    }
    // sudo 没问题，直接执行
    await sendMessage(message, true);
  };

  const sendMessage = async (message: string, confirmed = false) => {
    if (!message.trim()) return;

    // 取消操作 - 更新风险警告框为已取消状态
    if (message === 'cancel' && !confirmed) {
      setMessages(prev => prev.map(m =>
        m.needsConfirmation ? { ...m, needsConfirmation: false, confirmedAction: 'cancelled' } : m
      ));
      setIsLoading(true);
      try {
        await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'cancel', confirmed: false, server_id: currentServer, session_id: currentSessionId }),
        });
      } catch (e) { /* ignore */ }
      setIsLoading(false);
      return;
    }

    // 确认操作 - 更新风险警告框为执行中状态
    if (confirmed) {
      setMessages(prev => prev.map(m =>
        m.needsConfirmation ? { ...m, needsConfirmation: false, confirmedAction: 'executing' } : m
      ));
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: confirmed
        ? (language === 'zh' ? '✅ 好的，执行' : '✅ Go ahead')
        : message,
      timestamp: new Date(),
      serverId: currentServer,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, confirmed, server_id: currentServer, session_id: currentSessionId }),
      });

      const data = await response.json();

      // 确认后，将执行中状态更新为已完成
      if (confirmed) {
        setMessages(prev => prev.map(m =>
          m.confirmedAction === 'executing' ? { ...m, confirmedAction: 'confirmed' } : m
        ));
      }

      const agentMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'agent',
        content: data.message,
        commands: data.commands_executed,
        riskLevel: data.risk_level,
        needsConfirmation: data.needs_confirmation,
        originalInput: data.needs_confirmation ? message : undefined,
        timestamp: new Date(),
        serverId: data.server_id,
      };

      setMessages((prev) => [...prev, agentMessage]);

      if (checkSudoNeeded(data.message)) {
        pendingSudoCmdRef.current = message;
        setShowSudoModal(true);
      }

      if (currentSessionId !== 'default') {
        fetchSessions();
      }

      if (voiceEnabled && !data.needs_confirmation) {
        speak(data.message);
      }
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'agent',
        content: '错误：连接服务器失败',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputValue);
    }
  };

  const toggleLanguage = () => {
    setLanguage((prev) => (prev === 'zh' ? 'en' : 'zh'));
  };

  const toggleVoice = () => {
    const newState = !voiceEnabled;
    setVoiceEnabled(newState);
    if (!newState) {
      speechSynthesis.cancel();
    }
  };

  const currentServerInfo = servers.find(s => s.id === currentServer);

  const quickCommands = [
    { label: t.disk, cmd: t.diskCmd },
    { label: t.process, cmd: t.processCmd },
    { label: t.memory, cmd: t.memoryCmd },
    { label: t.network, cmd: t.networkCmd },
  ];

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <span className="logo-icon">OS</span>
            <span className="logo-text">Agent</span>
          </div>
          <button className="lang-btn" onClick={toggleLanguage}>
            {language === 'zh' ? 'EN' : '中'}
          </button>
        </div>

        <div className="sidebar-section">
          <div className="section-header">
            <h3>💬 {t.sessionHistory}</h3>
            <button className="new-session-btn" onClick={createNewSession} title={t.newSession}>
              + {t.newSession}
            </button>
          </div>
          <div className="session-list">
            <div
              className={`session-item ${currentSessionId === 'default' ? 'active' : ''}`}
              onClick={() => switchSession('default')}
            >
              <div className="session-title">📌 {t.defaultMessage}</div>
            </div>
            {sessions.map((session) => (
              <div
                key={session.id}
                className={`session-item ${currentSessionId === session.id ? 'active' : ''}`}
                onClick={() => switchSession(session.id)}
              >
                <div className="session-info">
                  <div className="session-title">{session.title}</div>
                  <div className="session-meta">{session.message_count} {t.messagesCount}</div>
                </div>
                <button
                  className="session-delete-btn"
                  title={t.deleteSession}
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(session.id);
                  }}
                >
                  ×
                </button>
              </div>
            ))}
            {sessions.length === 0 && (
              <div className="session-empty">{t.noHistory}</div>
            )}
          </div>
        </div>

        <div className="sidebar-section">
          <h3>🖥️ {t.serverManagement}</h3>
          <div className="server-list">
            {servers.map((server) => (
              <div
                key={server.id}
                className={`server-item ${currentServer === server.id ? 'active' : ''}`}
                onClick={() => {
                  if (server.status === 'connected') {
                    setCurrentServer(server.id);
                  }
                }}
              >
                <div className="server-info">
                  <div className="server-name">{server.name}</div>
                  <div className="server-host">{server.host}</div>
                  <div className="server-meta">
                    {server.status === 'connected' ? (server.distro_name || server.os_name || '-') : '-'}
                  </div>
                </div>
                {server.status === 'connected' ? (
                  server.id === 'local' ? (
                    <div className="server-status connected">
                      {t.connected}
                    </div>
                  ) : (
                    <button
                      className="disconnect-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        disconnectServer(server);
                      }}
                    >
                      {t.disconnect}
                    </button>
                  )
                ) : server.status === 'connecting' ? (
                  <div className="server-status connecting">
                    {t.connecting}
                  </div>
                ) : server.status === 'error' ? (
                  <div className="server-actions">
                    <button
                      className="server-action-btn edit-btn"
                      title={t.editServer}
                      onClick={(e) => {
                        e.stopPropagation();
                        startEditServer(server);
                      }}
                    >
                      {t.editServer}
                    </button>
                    <button
                      className="connect-btn error"
                      onClick={(e) => {
                        e.stopPropagation();
                        connectServer(server);
                      }}
                    >
                      {t.retry}
                    </button>
                    {server.id !== 'local' && (
                      <button
                        className="server-action-btn delete-btn"
                        title={t.deleteServer}
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteServer(server);
                        }}
                      >
                        {t.deleteServer}
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="server-actions">
                    <button
                      className="connect-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        connectServer(server);
                      }}
                    >
                      {t.connect}
                    </button>
                    {server.id !== 'local' && (
                      <button
                        className="server-action-btn delete-btn"
                        title={t.deleteServer}
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteServer(server);
                        }}
                      >
                        {t.deleteServer}
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
            <button className="add-server-btn" onClick={() => setShowAddServer(true)}>
              + {t.addServer}
            </button>
          </div>
        </div>

        {showAddServer && (
          <div className="modal-overlay" onClick={() => setShowAddServer(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h3>{t.addServer}</h3>
              <div className="form-group">
                <label>{t.serverName}</label>
                <input
                  type="text"
                  value={newServer.name}
                  onChange={(e) => setNewServer(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="My Ubuntu Server"
                />
              </div>
              <div className="form-group">
                <label>{t.serverHost}</label>
                <input
                  type="text"
                  value={newServer.host}
                  onChange={(e) => setNewServer(prev => ({ ...prev, host: e.target.value }))}
                  placeholder="192.168.1.100"
                />
              </div>
              <div className="form-group">
                <label>{t.serverPort}</label>
                <input
                  type="number"
                  value={newServer.port}
                  onChange={(e) => setNewServer(prev => ({ ...prev, port: parseInt(e.target.value) || 22 }))}
                />
              </div>
              <div className="form-group">
                <label>{t.serverUser}</label>
                <input
                  type="text"
                  value={newServer.username}
                  onChange={(e) => setNewServer(prev => ({ ...prev, username: e.target.value }))}
                  placeholder="root"
                />
              </div>
              <div className="form-group">
                <label>{t.authType}</label>
                <select
                  value={newServer.auth_type}
                  onChange={(e) => setNewServer(prev => ({ ...prev, auth_type: e.target.value }))}
                >
                  <option value="password">{t.passwordAuth}</option>
                  <option value="key">{t.keyAuth}</option>
                </select>
              </div>
              {newServer.auth_type === 'key' ? (
                <div className="form-group">
                  <label>{t.keyPath}</label>
                  <input
                    type="text"
                    value={newServer.key_path}
                    onChange={(e) => setNewServer(prev => ({ ...prev, key_path: e.target.value }))}
                    placeholder="~/.ssh/id_rsa"
                  />
                </div>
              ) : (
                <div className="form-group">
                  <label>{t.password}</label>
                  <input
                    type="password"
                    value={newServer.password}
                    onChange={(e) => setNewServer(prev => ({ ...prev, password: e.target.value }))}
                  />
                </div>
              )}
              <div className="modal-actions">
                <button className="btn-secondary" onClick={() => setShowAddServer(false)}>
                  {t.cancel}
                </button>
                <button className="btn-primary" onClick={addNewServer}>
                  {t.connect}
                </button>
              </div>
            </div>
          </div>
        )}

        {editingServer && (
          <div className="modal-overlay" onClick={() => setEditingServer(null)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h3>{t.editServer} - {editingServer.name}</h3>
              <div className="form-group">
                <label>{t.serverName}</label>
                <input
                  type="text"
                  value={editForm.name}
                  onChange={(e) => setEditForm(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="My Ubuntu Server"
                />
              </div>
              <div className="form-group">
                <label>{t.serverHost}</label>
                <input
                  type="text"
                  value={editForm.host}
                  onChange={(e) => setEditForm(prev => ({ ...prev, host: e.target.value }))}
                  placeholder="192.168.1.100"
                />
              </div>
              <div className="form-group">
                <label>{t.serverPort}</label>
                <input
                  type="number"
                  value={editForm.port}
                  onChange={(e) => setEditForm(prev => ({ ...prev, port: parseInt(e.target.value) || 22 }))}
                />
              </div>
              <div className="form-group">
                <label>{t.serverUser}</label>
                <input
                  type="text"
                  value={editForm.username}
                  onChange={(e) => setEditForm(prev => ({ ...prev, username: e.target.value }))}
                  placeholder="root"
                />
              </div>
              <div className="form-group">
                <label>{t.authType}</label>
                <select
                  value={editForm.auth_type}
                  onChange={(e) => setEditForm(prev => ({ ...prev, auth_type: e.target.value }))}
                >
                  <option value="password">{t.passwordAuth}</option>
                  <option value="key">{t.keyAuth}</option>
                </select>
              </div>
              {editForm.auth_type === 'key' ? (
                <div className="form-group">
                  <label>{t.keyPath}</label>
                  <input
                    type="text"
                    value={editForm.key_path}
                    onChange={(e) => setEditForm(prev => ({ ...prev, key_path: e.target.value }))}
                    placeholder="~/.ssh/id_rsa"
                  />
                </div>
              ) : (
                <div className="form-group">
                  <label>{t.password}</label>
                  <input
                    type="password"
                    value={editForm.password}
                    onChange={(e) => setEditForm(prev => ({ ...prev, password: e.target.value }))}
                  />
                </div>
              )}
              <div className="modal-actions">
                <button className="btn-secondary" onClick={() => setEditingServer(null)}>
                  {t.cancel}
                </button>
                <button className="btn-primary" onClick={saveEditServer}>
                  {t.save}
                </button>
              </div>
            </div>
          </div>
        )}

        {showSudoModal && (
          <div className="modal-overlay">
            <div className="modal sudo-modal" onClick={(e) => e.stopPropagation()}>
              <h3>🔐 {t.sudoTitle}</h3>
              <p className="sudo-desc">{t.sudoDesc}</p>
              <div className="form-group">
                <input
                  type="password"
                  value={sudoPassword}
                  onChange={(e) => setSudoPassword(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') submitSudoPassword(); }}
                  placeholder={t.sudoPlaceholder}
                  autoFocus
                />
              </div>
              <div className="modal-actions">
                <button className="btn-secondary" disabled={sudoSubmitting} onClick={() => { setShowSudoModal(false); setSudoPassword(''); pendingSudoCmdRef.current = null; pendingConfirmRef.current = null; }}>
                  {t.sudoSkip}
                </button>
                <button className="btn-primary" disabled={sudoSubmitting} onClick={submitSudoPassword}>
                  {sudoSubmitting ? '验证中...' : t.sudoSubmit}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="sidebar-section">
          <h3>💡 {t.capabilities}</h3>
          <div className="capability-list">
            {capabilities.map((cap, index) => (
              <div
                key={index}
                className="capability-item"
                onClick={() => setInputValue(cap.description)}
              >
                <div className="capability-name">{cap.name}</div>
                <div className="capability-desc">{cap.actions.join(', ')}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-section">
          <h3>⚡ {t.quickCommands}</h3>
          <div className="quick-cmd-list">
            {quickCommands.map((cmd, index) => (
              <div key={index} className="quick-cmd-item" onClick={() => sendMessage(cmd.cmd)}>
                {cmd.label}
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-section">
          <h3>🎯 {t.currentTarget}</h3>
          <div className="info-grid">
            <div className="info-row">
              <span className="info-label">🖥️ {t.hostname}</span>
              <span className="info-value">{currentServerInfo?.name || '-'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">💿 {t.os}</span>
              <span className="info-value">
                {currentServer === 'local' 
                  ? (systemInfo.os_name || '-') 
                  : (currentServerInfo?.os_name || '-')}
              </span>
            </div>
            <div className="info-row">
              <span className="info-label">📦 {t.distro}</span>
              <span className="info-value">
                {currentServer === 'local' 
                  ? (systemInfo.distro_name || '-') 
                  : (currentServerInfo?.distro_name || '-')}
              </span>
            </div>
            <div className="info-row">
              <span className="info-label">🔧 {t.kernel}</span>
              <span className="info-value">{systemInfo.kernel || '-'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">👤 {t.currentUser}</span>
              <span className="info-value">{systemInfo.current_user || '-'}</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="chat-area">
        <div className="chat-header">
          <h1>{t.title}</h1>
          <div className="header-actions">
            <span className="status-badge">{t.online}</span>
            <button
              className={`btn-icon ${voiceEnabled ? 'active' : ''}`}
              onClick={toggleVoice}
              title={t.voiceOutput}
            >
              {voiceEnabled ? '🔊' : '🔇'}
            </button>
            <button className="btn-secondary" onClick={() => {
              setMessages([]);
              fetch('/api/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: currentSessionId }),
              }).catch(() => {});
            }}>
              {t.clearChat}
            </button>
          </div>
        </div>

        <div className="messages-container">
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-icon">OS Agent</div>
              <h2>{t.welcome}</h2>
              <p>{t.welcomeDesc}</p>
                <div className="welcome-examples">
                {quickCommands.map((cmd, index) => (
                  <div key={index} className={`example-item ${isLoading ? 'disabled' : ''}`} onClick={() => !isLoading && sendMessage(cmd.cmd)}>
                    {cmd.cmd}
                  </div>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.type}`}>
              {msg.needsConfirmation ? (
                <div className="risk-warning">
                  <div className="risk-title">
                    {msg.riskLevel === 'critical' ? t.highRiskWarning : t.riskWarning}
                  </div>
                  <div className="risk-desc">{msg.content}</div>
                  <div className="risk-actions">
                    <button disabled={isLoading} onClick={() => sendMessage('cancel', false)}>{t.cancel}</button>
                    <button className="confirm" disabled={isLoading} onClick={() => handleConfirm(msg.originalInput || msg.content)}>
                      {isLoading ? t.checking : t.confirm}
                    </button>
                  </div>
                </div>
              ) : msg.confirmedAction === 'executing' ? (
                <div className="risk-result executing">
                  <div className="risk-result-icon">⏳</div>
                  <div className="risk-result-text">
                    <div className="risk-result-title">{language === 'zh' ? '正在执行...' : 'Executing...'}</div>
                    <div className="risk-result-desc">{msg.content}</div>
                  </div>
                </div>
              ) : msg.confirmedAction === 'confirmed' ? (
                <div className="risk-result confirmed">
                  <div className="risk-result-icon">✅</div>
                  <div className="risk-result-text">
                    <div className="risk-result-title">{language === 'zh' ? '执行完成' : 'Completed'}</div>
                    <div className="risk-result-desc">{msg.content}</div>
                  </div>
                </div>
              ) : msg.confirmedAction === 'cancelled' ? (
                <div className="risk-result cancelled">
                  <div className="risk-result-icon">❌</div>
                  <div className="risk-result-text">
                    <div className="risk-result-title">{language === 'zh' ? '已取消' : 'Cancelled'}</div>
                    <div className="risk-result-desc">{msg.content}</div>
                  </div>
                </div>
              ) : (
                <div className="message-content">
                  {msg.commands && msg.commands.length > 0 && (
                    <div className="command-output">
                      <div className="command-label">$ {msg.commands.join(' && ')}</div>
                    </div>
                  )}
                  <div className="message-text">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                  <div className="message-time">
                    {msg.serverId && msg.serverId !== 'local' && `[${msg.serverId}] `}
                    {msg.timestamp.toLocaleTimeString()}
                  </div>
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="message agent">
              <div className="loading">
                <span></span>
                <span></span>
                <span></span>
                <span className="loading-text">{t.checking}</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          <button
            className={`voice-btn ${isListening ? 'listening' : ''}`}
            onClick={toggleVoiceInput}
            title={t.voiceInput}
          >
            {isListening ? '...' : 'MIC'}
          </button>
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isListening ? t.listening : t.enterCommand}
            rows={1}
          />
          <button onClick={() => sendMessage(inputValue)} disabled={isLoading || !inputValue.trim()}>
            {t.send}
          </button>
        </div>
      </main>
    </div>
  );
}

export default App;
