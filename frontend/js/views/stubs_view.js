export const stubsViewTemplate = `
<section class="panel">
  <h2>增补入笼 · 重核衔接</h2>
  <div class="stub-banner">
    <strong>甲路径（已锁死）</strong>：
    增补提交、扩额、作废旧核验、笼改「待重核」与审计同事务完成；失败则增补与作废同滚。
    重核前解笼与罚没口一律关闭，禁止只改提醒字。
    <div class="hint" style="margin:6px 0 0">
      纪要：{{ recheck.manifest && recheck.manifest.locked ? '已锁死 ' + (recheck.manifest.locked_at || '') : '未锁死：写入将被拒绝' }}
      · 待重核 {{ recheck.pending_count || 0 }} 笼
      · 闸门规则 {{ recheck.gate_policy ? recheck.gate_policy.rule : '' }}
    </div>
  </div>
  <div class="grid-2">
    <div>
      <h3>增补入笼（甲路径）</h3>
      <div class="form-row">
        <div>
          <label>笼</label>
          <select v-model.number="topupForm.cage_id">
            <option :value="0">请选择</option>
            <option v-for="c in cages" :key="'t'+c.id" :value="c.id">
              {{ c.cage_code }} · {{ c.status }} · 可用 {{ fmt(c.available) }}
            </option>
          </select>
        </div>
        <div>
          <label>增补金额</label>
          <input type="number" v-model.number="topupForm.amount" min="1"/>
        </div>
        <div>
          <label>模式（唯一放行）</label>
          <select v-model="topupForm.mode">
            <option>同笼扩代</option>
          </select>
        </div>
        <div>
          <label>路径（唯一放行）</label>
          <input value="甲" disabled/>
        </div>
      </div>
      <div class="actions">
        <button @click="doTopup">提交增补并作废旧核验</button>
      </div>
      <h3 style="margin-top:12px">增补 job</h3>
      <table>
        <thead><tr><th>ID</th><th>笼</th><th>增补</th><th>额前→额后</th><th>状态</th><th>作废旧核验</th><th>出金口</th></tr></thead>
        <tbody>
          <tr v-for="j in topupJobs" :key="j.id">
            <td>{{ j.id }}</td>
            <td>{{ j.cage_code }}</td>
            <td>{{ fmt(j.amount) }}</td>
            <td>{{ fmt(j.amount_before) }} → {{ fmt(j.amount_after) }}</td>
            <td>{{ j.status }}</td>
            <td>{{ j.voided_attestation_id || '—' }}</td>
            <td>
              <span class="badge" :class="j.recheck_required ? 'fail' : 'pass'">
                {{ j.recheck_required ? '关闭·待重核' : '已重核放行' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div>
      <h3>待重核清单（五页同源）</h3>
      <p class="hint">与核验 / 解笼 / 罚没 / 审计页读同一 /api/recheck/board。</p>
      <table>
        <thead><tr><th>笼</th><th>状态</th><th>额前→当前</th><th>作废旧核验</th><th>出金口</th></tr></thead>
        <tbody>
          <tr v-for="p in recheckPending" :key="'p'+p.cage_id">
            <td>{{ p.cage_code }}</td>
            <td>{{ p.status }}</td>
            <td>{{ fmt(p.amount_before) }} → {{ fmt(p.amount) }}</td>
            <td>{{ p.voided_attestation_ids.join(', ') || '—' }}</td>
            <td><span class="badge fail">关闭</span></td>
          </tr>
          <tr v-if="!recheckPending.length">
            <td colspan="5" class="hint">无待重核笼</td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:14px">重核偏航</h3>
      <table>
        <thead><tr><th>时间</th><th>人</th><th>目标</th><th>载荷</th></tr></thead>
        <tbody>
          <tr v-for="d in (recheck.deviations||[])" :key="'d'+d.id">
            <td>{{ d.created_at }}</td>
            <td>{{ d.actor }}</td>
            <td>{{ d.target }}</td>
            <td><code style="font-size:11px">{{ d.payload }}</code></td>
          </tr>
          <tr v-if="!(recheck.deviations||[]).length">
            <td colspan="4" class="hint">无偏航记录</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <h2 style="margin-top:18px">拆笼分拨（仍为空桩）</h2>
  <div class="grid-2">
    <div>
      <div class="form-row">
        <div>
          <label>笼</label>
          <select v-model.number="splitForm.cage_id">
            <option :value="0">请选择</option>
            <option v-for="c in cages" :key="'s'+c.id" :value="c.id">
              {{ c.cage_code }} · 可用 {{ fmt(c.available) }}
            </option>
          </select>
        </div>
        <div>
          <label>左金额</label>
          <input type="number" v-model.number="splitForm.left_amount" min="1"/>
        </div>
        <div>
          <label>右金额</label>
          <input type="number" v-model.number="splitForm.right_amount" min="1"/>
        </div>
        <div>
          <label>模式</label>
          <select v-model="splitForm.mode">
            <option>整笔切分</option>
            <option>影子子笼</option>
          </select>
        </div>
      </div>
      <div class="actions">
        <button @click="doSplitStub">登记拆笼空桩</button>
      </div>
    </div>
    <div>
      <table>
        <thead><tr><th>ID</th><th>笼</th><th>左</th><th>右</th><th>模式</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="j in splitJobs" :key="j.id">
            <td>{{ j.id }}</td>
            <td>{{ j.cage_code }}</td>
            <td>{{ fmt(j.left_amount) }}</td>
            <td>{{ fmt(j.right_amount) }}</td>
            <td>{{ j.mode }}</td>
            <td>{{ j.status }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
`;
