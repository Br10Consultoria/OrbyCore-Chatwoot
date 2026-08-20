# frozen_string_literal: true

require 'json'
require 'securerandom'
require 'uri'

def required_env(name)
  value = ENV[name].to_s.strip
  raise "Variavel obrigatoria ausente: #{name}" if value.empty?

  value
end

account_id = ENV['ORBY_ACCOUNT_ID'].to_s.strip
inbox_name = ENV.fetch('ORBY_INBOX_NAME', 'Portal Sac').strip
portal_url = required_env('ORBY_PORTAL_URL')
webhook_url = required_env('ORBY_WEBHOOK_URL')
integration_email = required_env('ORBY_INTEGRATION_EMAIL').downcase
rotate_hmac = ActiveModel::Type::Boolean.new.cast(ENV.fetch('ORBY_ROTATE_HMAC', 'false'))

portal_uri = URI.parse(portal_url)
raise 'ORBY_PORTAL_URL precisa usar http ou https' unless %w[http https].include?(portal_uri.scheme) && portal_uri.host

portal_origin = "#{portal_uri.scheme}://#{portal_uri.host}"
default_port = portal_uri.scheme == 'https' ? 443 : 80
portal_origin += ":#{portal_uri.port}" unless portal_uri.port == default_port

result = ActiveRecord::Base.transaction do
  account = if account_id.empty?
              accounts = Account.order(:id).to_a
              raise 'Nenhuma conta foi criada no Chatwoot' if accounts.empty?
              raise 'Existe mais de uma conta; defina CHATWOOT_ACCOUNT_ID no .env' if accounts.many?

              accounts.first
            else
              Account.find(account_id)
            end

  inbox = account.inboxes
                 .where(channel_type: 'Channel::WebWidget')
                 .where('LOWER(name) = ?', inbox_name.downcase)
                 .first

  unless inbox
    channel = account.web_widgets.create!(
      website_url: portal_url,
      allowed_domains: portal_origin,
      hmac_mandatory: true
    )
    inbox = account.inboxes.create!(name: inbox_name, channel: channel)
  end

  channel = inbox.channel
  raise "A caixa #{inbox.name} nao e do tipo Website" unless channel.is_a?(Channel::WebWidget)

  channel.update!(
    website_url: portal_url,
    allowed_domains: portal_origin,
    hmac_mandatory: true
  )
  channel.regenerate_website_token if channel.website_token.blank?
  channel.regenerate_hmac_token if rotate_hmac || channel.hmac_token.blank?

  integration_user = User.find_or_initialize_by(email: integration_email)
  if integration_user.new_record?
    password = SecureRandom.urlsafe_base64(48)
    integration_user.assign_attributes(
      name: 'OrbyCore Integration',
      password: password,
      password_confirmation: password
    )
    integration_user.skip_confirmation! if integration_user.respond_to?(:skip_confirmation!)
    integration_user.save!
  end

  integration_membership = AccountUser.find_or_create_by!(account: account, user: integration_user) do |membership|
    membership.role = :agent
  end
  integration_membership.update!(availability: :offline, auto_offline: true)
  InboxMember.find_or_create_by!(inbox: inbox, user: integration_user)
  account.administrators.find_each do |administrator|
    InboxMember.find_or_create_by!(inbox: inbox, user: administrator)
  end

  api_access_token = integration_user.access_token || AccessToken.create!(owner: integration_user)
  subscriptions = %w[message_created conversation_created conversation_status_changed]
  webhook = account.webhooks.find_or_initialize_by(name: 'OrbyCore Bridge')
  webhook.assign_attributes(
    name: 'OrbyCore Bridge',
    url: webhook_url,
    subscriptions: subscriptions,
    webhook_type: :account_type,
    inbox: nil
  )
  webhook.save!

  {
    account_id: account.id,
    inbox_id: inbox.id,
    api_token: api_access_token.token,
    website_token: channel.website_token,
    hmac_token: channel.hmac_token,
    integration_email: integration_user.email,
    webhook_id: webhook.id,
    portal_origin: portal_origin
  }
end
puts "ORBYCHAT_CONFIG=#{JSON.generate(result)}"
