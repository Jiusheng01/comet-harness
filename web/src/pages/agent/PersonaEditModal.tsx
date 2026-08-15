import { useEffect, useState } from 'react'
import {
  Button,
  Input,
  Modal,
  Slider,
  Space,
  Upload,
  message as antdMessage,
} from 'antd'
import { CameraOutlined, CloseCircleFilled, ThunderboltOutlined } from '@ant-design/icons'
import { chatApi } from '@/api/chat'
import { personaApi, type Persona, type PersonaPayload } from '@/api/personas'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import { personaGradientCss, personaInitial } from './personaGradient'

interface Props {
  open: boolean
  persona: Persona | null
  onClose: () => void
  onSaved: () => void
}

export default function PersonaEditModal({ open, persona, onClose, onSaved }: Props) {
  const [name, setName] = useState('')
  const [prompt, setPrompt] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [avatarKey, setAvatarKey] = useState<string | null>(null)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const [optimizing, setOptimizing] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName(persona?.name ?? '')
      setPrompt(persona?.system_prompt ?? '')
      setTemperature(persona?.temperature ?? 0.7)
      setAvatarKey(persona?.avatar_key ?? null)
      setAvatarUrl(persona?.avatar_url ?? null)
    }
  }, [open, persona])

  const onOptimize = async () => {
    const raw = prompt.trim()
    if (!raw) {
      antdMessage.warning('请先填写人设提示词')
      return
    }
    setOptimizing(true)
    try {
      const { data } = await personaApi.optimizePrompt(raw)
      setPrompt(data.optimized)
      antdMessage.success('已优化，可继续微调')
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setOptimizing(false)
    }
  }

  const onUpload = async (file: File) => {
    const { data } = await chatApi.uploadImage(file)
    setAvatarKey(data.file_key)
    setAvatarUrl(data.url)
    return false
  }

  const onSave = async () => {
    const payload: PersonaPayload = {
      name: name.trim(),
      avatar_key: avatarKey ?? '',
      system_prompt: prompt,
      temperature,
    }
    setSaving(true)
    try {
      if (persona) {
        await personaApi.update(persona.id, payload)
      } else {
        await personaApi.create(payload)
      }
      onSaved()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onCancel={onClose} onOk={onSave} confirmLoading={saving} title="角色">
      <div>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="角色名" />
        <Input.TextArea value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        <Space>
          <Button icon={<ThunderboltOutlined />} loading={optimizing} onClick={onOptimize}>
            优化提示词
          </Button>
          {avatarUrl && <Button icon={<CloseCircleFilled />} onClick={() => setAvatarUrl(null)}>移除头像</Button>}
        </Space>
        <Upload beforeUpload={onUpload} showUploadList={false}><Button icon={<CameraOutlined />}>上传头像</Button></Upload>
        <Slider min={0} max={2} step={0.1} value={temperature} onChange={setTemperature} />
      </div>
    </Modal>
  )
}
