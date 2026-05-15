import { useEffect, useState } from "react";
import {
  Button, Card, Checkbox, Input, List, Modal, Space, Switch, Tag, Typography, message,
} from "antd";
import { useParams } from "react-router-dom";
import { api } from "../api/client";

interface Chunk {
  id: number;
  chunk_index: number;
  text: string;
  is_active: boolean;
}

export default function DocumentDetailPage() {
  const { id } = useParams();
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [editing, setEditing] = useState<Chunk | null>(null);
  const [editText, setEditText] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const load = async () => {
    const r = await api.get(`/api/documents/${id}/chunks`);
    setChunks(r.data);
  };
  useEffect(() => { load(); }, [id]);

  const toggle = async (c: Chunk) => {
    await api.post(`/api/chunks/${c.id}/toggle`, { is_active: !c.is_active });
    load();
  };

  const saveEdit = async () => {
    if (!editing) return;
    await api.patch(`/api/chunks/${editing.id}`, { text: editText });
    message.success("已保存（已重新生成向量）");
    setEditing(null); load();
  };

  const split = (c: Chunk) => {
    let pos = Math.floor(c.text.length / 2);
    Modal.confirm({
      title: `拆分切片 #${c.chunk_index}`,
      content: (
        <div>
          <div style={{ marginBottom: 8 }}>在哪个位置拆分（字符数，1-{c.text.length - 1}）</div>
          <Input type="number" defaultValue={pos} onChange={(e) => { pos = parseInt(e.target.value); }} />
        </div>
      ),
      onOk: async () => {
        await api.post(`/api/chunks/${c.id}/split`, { position: pos });
        message.success("已拆分");
        load();
      },
    });
  };

  const mergeSelected = async () => {
    if (selected.size < 2) return message.warning("至少选择 2 个相邻切片");
    await api.post(`/api/chunks/merge`, { chunk_ids: Array.from(selected) });
    message.success("已合并");
    setSelected(new Set()); load();
  };

  const toggleSelect = (id: number, on: boolean) => {
    const s = new Set(selected);
    on ? s.add(id) : s.delete(id);
    setSelected(s);
  };

  return (
    <Card
      title={`文档 #${id} - 切片管理（${chunks.length}）`}
      extra={
        <Space>
          <span style={{ color: "#888" }}>已选 {selected.size}</span>
          <Button onClick={mergeSelected} disabled={selected.size < 2}>合并所选</Button>
          <Button onClick={() => setSelected(new Set())} disabled={!selected.size}>取消选择</Button>
        </Space>
      }
    >
      <List
        dataSource={chunks}
        renderItem={(c) => (
          <List.Item
            actions={[
              <a onClick={() => { setEditing(c); setEditText(c.text); }}>编辑</a>,
              <a onClick={() => split(c)}>拆分</a>,
              <Switch checked={c.is_active} size="small" onChange={() => toggle(c)} />,
            ]}
          >
            <Checkbox
              checked={selected.has(c.id)}
              onChange={(e) => toggleSelect(c.id, e.target.checked)}
              style={{ marginRight: 12 }}
            />
            <List.Item.Meta
              title={
                <Space>
                  <Tag>#{c.chunk_index}</Tag>
                  <Typography.Text type={c.is_active ? undefined : "secondary"}>
                    长度 {c.text.length}
                  </Typography.Text>
                  {!c.is_active && <Tag color="default">已禁用</Tag>}
                </Space>
              }
              description={
                <pre style={{
                  whiteSpace: "pre-wrap", margin: 0,
                  color: c.is_active ? undefined : "#aaa",
                }}>{c.text}</pre>
              }
            />
          </List.Item>
        )}
      />

      <Modal
        title={`编辑切片 #${editing?.chunk_index}`}
        open={!!editing}
        onOk={saveEdit}
        onCancel={() => setEditing(null)}
        width={720}
        okText="保存并重新向量化"
      >
        <Input.TextArea rows={12} value={editText} onChange={(e) => setEditText(e.target.value)} />
      </Modal>
    </Card>
  );
}
