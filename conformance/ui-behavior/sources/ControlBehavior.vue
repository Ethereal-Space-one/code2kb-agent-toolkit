<template>
  <view>
    <view class="report-form">
      <text>报送表单</text>
      <input v-model="draft" :disabled="phase === 'pending'" placeholder="填写报送内容" />
      <button :disabled="!draft.trim() || phase === 'pending'"
              :loading="phase === 'pending'" @click="submitReport">提交</button>
      <text>{{ feedback }}</text>
      <button v-if="phase === 'failure'" @click="submitReport">重试</button>
    </view>

    <view class="local-confirmation">
      <text>本地确认区域</text>
      <button @click="openConfirmation">提交</button>
      <view v-if="dialogOpen" class="confirmation-dialog">
        <text>这里只展示本地确认说明，不发送报送请求。</text>
        <button @click="closeConfirmation">关闭</button>
      </view>
    </view>
  </view>
</template>

<script>
export default {
  props: {
    sendReport: { type: Function, required: true }
  },
  data() {
    return { draft: '', phase: 'idle', feedback: '', dialogOpen: false };
  },
  methods: {
    async submitReport() {
      if (!this.draft.trim() || this.phase === 'pending') return;
      this.phase = 'pending';
      this.feedback = '正在提交';
      try {
        await this.sendReport(this.draft.trim());
        this.phase = 'success';
        this.feedback = '提交请求已返回';
      } catch (error) {
        this.phase = 'failure';
        this.feedback = '提交失败，可重试';
      }
    },
    openConfirmation() {
      this.dialogOpen = true;
    },
    closeConfirmation() {
      this.dialogOpen = false;
    }
  }
};
</script>
