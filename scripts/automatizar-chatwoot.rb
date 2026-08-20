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
widget_color = ENV.fetch('ORBY_WIDGET_COLOR', '#087FAE').strip
welcome_title = ENV.fetch('ORBY_WIDGET_WELCOME_TITLE', 'Olá! Como podemos ajudar?').strip
welcome_tagline = ENV.fetch(
  'ORBY_WIDGET_WELCOME_TAGLINE',
  'Suporte técnico, financeiro e contratação em um só lugar.'
).strip
raise 'ORBY_WIDGET_COLOR precisa usar o formato hexadecimal #RRGGBB' unless widget_color.match?(/\A#[0-9a-fA-F]{6}\z/)

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
    hmac_mandatory: true,
    widget_color: widget_color,
    welcome_title: welcome_title,
    welcome_tagline: welcome_tagline,
    reply_time: :in_a_few_minutes
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
  inbox.update!(
    # O menu interativo é enviado pelo AgentBot. O greeting textual do inbox
    # escondia a falha do webhook e fazia o widget exibir apenas uma frase.
    greeting_enabled: false,
    greeting_message: '',
    enable_auto_assignment: false,
    allow_messages_after_resolved: true
  )

  agent_bot = account.agent_bots.find_or_initialize_by(name: 'OrbyCore Assistente')
  agent_bot.assign_attributes(
    description: 'Menus do Portal SAC e automações integradas ao OrbyCore/OrbySync.',
    outgoing_url: webhook_url,
    bot_type: :webhook
  )
  agent_bot.save!
  AgentBotInbox.find_or_create_by!(agent_bot: agent_bot, inbox: inbox)

  teams = {
    support: account.teams.find_or_create_by!(name: 'suporte técnico'),
    financial: account.teams.find_or_create_by!(name: 'financeiro'),
    commercial: account.teams.find_or_create_by!(name: 'comercial')
  }
  teams[:support].update!(description: 'Conexão, Wi-Fi, equipamentos e atendimento técnico.', icon: 'headset', icon_color: '#087FAE')
  teams[:financial].update!(description: 'Faturas, pagamentos, PIX e negociação.', icon: 'credit-card', icon_color: '#E87822')
  teams[:commercial].update!(description: 'Planos, contratação e mudanças de serviço.', icon: 'briefcase', icon_color: '#1C9B72')

  account.administrators.find_each do |administrator|
    InboxMember.find_or_create_by!(inbox: inbox, user: administrator)
    teams.each_value do |team|
      TeamMember.find_or_create_by!(team: team, user: administrator)
    end
  end

  # Mensagens criadas com o token do bot preservam sender_type=AgentBot e são
  # renderizadas pelo widget como input_select clicável.
  api_access_token = agent_bot.access_token || AccessToken.create!(owner: agent_bot)
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
    agent_bot_id: agent_bot.id,
    api_token: api_access_token.token,
    website_token: channel.website_token,
    hmac_token: channel.hmac_token,
    integration_email: integration_user.email,
    webhook_id: webhook.id,
    portal_origin: portal_origin,
    team_support_id: teams[:support].id,
    team_financial_id: teams[:financial].id,
    team_commercial_id: teams[:commercial].id
  }
end
puts "ORBYCHAT_CONFIG=#{JSON.generate(result)}"
