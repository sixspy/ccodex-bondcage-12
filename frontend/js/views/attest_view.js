export const attestViewTemplate = `
<section class="panel">
  <h2>履约核验</h2>
  <p class="hint">
    已冻结笼可首核；增补后的笼处于「待重核」，须用新金额重新裁定，旧结论已作废不得改口。
    同笼代只允许一条有效结论，作废行保留痕。数据与增补 / 解笼 / 罚没 / 审计页同源。
  </p>
  <div class="grid-2">
    <div>
      <div class="form-row">
        <div>
          <label>笼</label>
          <select v-model.number="attestForm.cage_id">
            <option :value="0">请选择</option>
            <option v-for="c in frozenCages" :key="c.id" :value="c.id">
              {{ c.cage_code }} · {{ c.status }} · {{ fmt(c.available) }} · 代{{ c.generation }}
            </option>
          </select>
        </div>
        <div>
          <label>结论</label>
          <select v-model="attestForm.outcome">
            <option>通过</option>
            <option>违约</option>
          </select>
        </div>
        <div style="grid-column:1/-1">
          <label>证据摘要</label>
          <textarea v-model="attestForm.evidence" placeholder="验收单号 / 违约说明 / 新额复检单号"></textarea>
        </div>
      </div>
      <div v-if="recheckFor(attestForm.cage_id)" class="proof-box" style="margin-bottom:10px">
待重核：作废旧核验 {{ recheckFor(attestForm.cage_id).voided_attestation_ids.join(', ') || '—' }}
增补单 #{{ recheckFor(attestForm.cage_id).topup_job_id }}
额前 {{ fmt(recheckFor(attestForm.cage_id).amount_before) }} → 当前 {{ fmt(recheckFor(attestForm.cage_id).amount) }}
出金口 {{ recheckFor(attestForm.cage_id).gate === 'open' ? '开启' : '关闭' }}
      </div>
      <div class="actions">
        <button class="ok" @click="doAttest">提交核验</button>
      </div>
    </div>
    <div>
      <h3>待重核（五页同源）</h3>
      <table>
        <thead><tr><th>笼</th><th>额前→当前</th><th>作废旧核验</th><th>闸门</th></tr></thead>
        <tbody>
          <tr v-for="p in recheckPending" :key="'p'+p.cage_id">
            <td>{{ p.cage_code }}</td>
            <td>{{ fmt(p.amount_before) }} → {{ fmt(p.amount) }}</td>
            <td>{{ p.voided_attestation_ids.join(', ') || '—' }}</td>
            <td><span class="badge fail">关闭</span></td>
          </tr>
          <tr v-if="!recheckPending.length">
            <td colspan="4" class="hint">无待重核笼</td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:14px">核验记录</h3>
      <table>
        <thead>
          <tr><th>时间</th><th>笼</th><th>结论</th><th>笼代</th><th>核验员</th><th>作废</th><th>证据</th></tr>
        </thead>
        <tbody>
          <tr v-for="a in attestations" :key="a.id">
            <td>{{ a.created_at }}</td>
            <td>{{ a.cage_code }}</td>
            <td><span class="badge" :class="a.outcome==='通过'?'pass':'fail'">{{ a.outcome }}</span></td>
            <td>{{ a.attest_gen }}</td>
            <td>{{ a.officer }}</td>
            <td>
              <span v-if="a.voided_at" class="badge fail" :title="a.void_reason">
                已作废 · {{ a.void_reason }}
              </span>
              <span v-else class="badge pass">有效</span>
            </td>
            <td>{{ a.evidence }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
`;
