export const auditViewTemplate = `
<section class="panel">
  <h2>审计争用</h2>
  <p class="hint">写动作落审计；后到争用只记 contention，不写业务。增补重核偏航（recheck_deviation）与五页同源闸门同读一板。</p>
  <div class="grid-2">
    <div>
      <h3>审计</h3>
      <table>
        <thead><tr><th>时间</th><th>人</th><th>动作</th><th>目标</th><th>载荷</th></tr></thead>
        <tbody>
          <tr v-for="a in audits" :key="a.id">
            <td>{{ a.created_at }}</td>
            <td>{{ a.actor }}</td>
            <td>{{ a.action }}</td>
            <td>{{ a.target }}</td>
            <td><code style="font-size:11px">{{ a.payload }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div>
      <h3>待重核闸门（五页同源）</h3>
      <table>
        <thead><tr><th>笼</th><th>代</th><th>状态</th><th>额前→当前</th><th>作废旧核验</th><th>出金口</th></tr></thead>
        <tbody>
          <tr v-for="p in (recheck.cages||[])" :key="'a'+p.cage_id">
            <td>{{ p.cage_code }}</td>
            <td>{{ p.generation }}</td>
            <td>{{ p.status }}</td>
            <td>{{ fmt(p.amount_before) }} → {{ fmt(p.amount) }}</td>
            <td>{{ p.voided_attestation_ids.join(', ') || '—' }}</td>
            <td>
              <span class="badge" :class="p.gate === 'open' ? 'pass' : 'fail'">
                {{ p.gate === 'open' ? '开启' : '关闭' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:14px">重核偏航</h3>
      <table>
        <thead><tr><th>时间</th><th>人</th><th>目标</th><th>载荷</th></tr></thead>
        <tbody>
          <tr v-for="d in (recheck.deviations||[])" :key="'dv'+d.id">
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
      <h3 style="margin-top:14px">持锁</h3>
      <table>
        <thead><tr><th>键</th><th>持有者</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="l in locks" :key="l.lock_key">
            <td>{{ l.lock_key }}</td>
            <td>{{ l.holder }}</td>
            <td>{{ l.acquired_at }}</td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:14px">争用</h3>
      <table>
        <thead><tr><th>时间</th><th>键</th><th>人</th><th>动作</th><th>详情</th></tr></thead>
        <tbody>
          <tr v-for="c in contention" :key="c.id">
            <td>{{ c.created_at }}</td>
            <td>{{ c.lock_key }}</td>
            <td>{{ c.actor }}</td>
            <td>{{ c.action }}</td>
            <td>{{ c.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
`;
