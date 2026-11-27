export const META_ACCOUNTS_CHANGED_EVENT = 'dm-karo-meta-accounts-changed'

export function notifyMetaAccountsChanged(): void {
  window.dispatchEvent(new Event(META_ACCOUNTS_CHANGED_EVENT))
}
