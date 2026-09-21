// CRM Module — MCP Tool Definitions
// Searches contact markdown files and interaction data.
// Plain JS (ESM) for direct dynamic import by the MCP server.

import { z } from '@datacore-one/mcp/runtime'
import * as fs from 'fs'
import * as path from 'path'

// --- Helpers ---

function findContactDirs(basePath) {
  const dirs = []
  try {
    for (const entry of fs.readdirSync(basePath)) {
      if (/^\d+-/.test(entry)) {
        const contactsPath = path.join(basePath, entry, 'contacts')
        if (fs.existsSync(contactsPath)) {
          dirs.push({ space: entry, path: contactsPath })
        }
        // Also check 3-knowledge/reference/people
        const refPath = path.join(basePath, entry, '3-knowledge', 'reference', 'people')
        if (fs.existsSync(refPath)) {
          dirs.push({ space: entry, path: refPath })
        }
      }
    }
  } catch { /* ignore */ }
  return dirs
}

function searchContacts(contactDirs, query) {
  const results = []
  const q = query.toLowerCase()

  for (const dir of contactDirs) {
    try {
      const walk = (dirPath) => {
        for (const entry of fs.readdirSync(dirPath)) {
          const fullPath = path.join(dirPath, entry)
          const stat = fs.statSync(fullPath)
          if (stat.isDirectory()) {
            walk(fullPath)
          } else if (entry.endsWith('.md') && !entry.startsWith('_')) {
            const name = entry.replace('.md', '').replace(/-/g, ' ')
            if (name.toLowerCase().includes(q)) {
              const content = fs.readFileSync(fullPath, 'utf-8').slice(0, 500)
              results.push({
                name,
                file: path.relative(dir.path, fullPath),
                space: dir.space,
                excerpt: content.split('\n').slice(0, 5).join('\n'),
              })
            }
          }
        }
      }
      walk(dir.path)
    } catch { /* ignore */ }
  }
  return results
}

// --- Tools ---

export const tools = [
  {
    name: 'lookup',
    description: 'Look up a contact or company by name across all spaces',
    inputSchema: z.object({
      name: z.string().describe('Contact or company name to search for'),
      space: z.string().optional().describe('Filter by space'),
    }),
    handler: async (args, ctx) => {
      let contactDirs = findContactDirs(ctx.storage.basePath)
      if (args.space) {
        contactDirs = contactDirs.filter(d => d.space === args.space)
      }

      const results = searchContacts(contactDirs, args.name)
      return { query: args.name, count: results.length, contacts: results.slice(0, 20) }
    },
  },

  {
    name: 'recent_interactions',
    description: 'Find recent interactions with contacts from journal entries',
    inputSchema: z.object({
      contact: z.string().optional().describe('Filter by contact name'),
      days: z.number().optional().describe('Lookback period in days (default: 14)'),
    }),
    handler: async (args, ctx) => {
      const days = args.days || 14
      const now = new Date()
      const interactions = []

      // Scan journal files for [[Contact]] mentions
      try {
        for (const entry of fs.readdirSync(ctx.storage.basePath)) {
          if (!/^\d+-/.test(entry)) continue
          const journalDir = path.join(ctx.storage.basePath, entry, 'journal')
          if (!fs.existsSync(journalDir)) continue

          for (const jf of fs.readdirSync(journalDir).sort().reverse()) {
            if (!jf.endsWith('.md')) continue
            const dateStr = jf.replace('.md', '')
            const fileDate = new Date(dateStr)
            const diffDays = (now - fileDate) / (1000 * 60 * 60 * 24)
            if (diffDays > days) break

            const content = fs.readFileSync(path.join(journalDir, jf), 'utf-8')
            const links = content.match(/\[\[([^\]]+)\]\]/g) || []
            for (const link of links) {
              const name = link.replace('[[', '').replace(']]', '')
              if (args.contact && !name.toLowerCase().includes(args.contact.toLowerCase())) continue
              interactions.push({ contact: name, date: dateStr, space: entry })
            }
          }
        }
      } catch { /* ignore */ }

      // Deduplicate by contact+date
      const seen = new Set()
      const unique = interactions.filter(i => {
        const key = `${i.contact}:${i.date}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })

      return { days, count: unique.length, interactions: unique.slice(0, 50) }
    },
  },

  {
    name: 'dormant',
    description: 'Find contacts with no recent interactions (dormant relationships)',
    inputSchema: z.object({
      threshold_days: z.number().optional().describe('Days without interaction to consider dormant (default: 60)'),
      space: z.string().optional().describe('Filter by space'),
    }),
    handler: async (args, ctx) => {
      const threshold = args.threshold_days || 60
      let contactDirs = findContactDirs(ctx.storage.basePath)
      if (args.space) {
        contactDirs = contactDirs.filter(d => d.space === args.space)
      }

      // Get all contacts
      const allContacts = searchContacts(contactDirs, '')

      // Get recent interactions
      const now = new Date()
      const recentContacts = new Set()

      try {
        for (const entry of fs.readdirSync(ctx.storage.basePath)) {
          if (!/^\d+-/.test(entry)) continue
          const journalDir = path.join(ctx.storage.basePath, entry, 'journal')
          if (!fs.existsSync(journalDir)) continue

          for (const jf of fs.readdirSync(journalDir).sort().reverse()) {
            if (!jf.endsWith('.md')) continue
            const dateStr = jf.replace('.md', '')
            const diffDays = (now - new Date(dateStr)) / (1000 * 60 * 60 * 24)
            if (diffDays > threshold) break

            const content = fs.readFileSync(path.join(journalDir, jf), 'utf-8')
            const links = content.match(/\[\[([^\]]+)\]\]/g) || []
            for (const link of links) {
              recentContacts.add(link.replace('[[', '').replace(']]', '').toLowerCase())
            }
          }
        }
      } catch { /* ignore */ }

      const dormant = allContacts.filter(c =>
        !recentContacts.has(c.name.toLowerCase())
      )

      return {
        threshold_days: threshold,
        total_contacts: allContacts.length,
        dormant_count: dormant.length,
        dormant: dormant.slice(0, 30),
      }
    },
  },
]
