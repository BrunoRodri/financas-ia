from datetime import timedelta
import decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Tag, CreditCard, RecurringRule, Transaction, Goal, UserSettings

class Command(BaseCommand):
    help = 'Limpa o banco de dados e cria registros simulados para testes de usabilidade.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Limpando dados existentes do banco...'))
        
        # 1. Limpar banco
        Transaction.objects.all().delete()
        RecurringRule.objects.all().delete()
        CreditCard.objects.all().delete()
        Tag.objects.all().delete()
        Goal.objects.all().delete()
        UserSettings.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS('Banco de dados limpo com sucesso!'))
        self.stdout.write(self.style.WARNING('Populando banco com dados simulados...'))
        
        today = timezone.localdate()
        
        # 2. Criar Configurações (UserSettings)
        # Saldo inicial de 5000.00 datado de hoje - 15 dias
        settings = UserSettings.load()
        settings.current_balance = decimal.Decimal('5000.00')
        settings.balance_date = today - timedelta(days=15)
        settings.save()
        self.stdout.write(self.style.SUCCESS('UserSettings criado com sucesso!'))
        
        # 3. Criar Tags
        tags_data = [
            {'name': 'Alimentação', 'color': '#f59e0b'},
            {'name': 'Lazer', 'color': '#ec4899'},
            {'name': 'Moradia', 'color': '#3b82f6'},
            {'name': 'Transporte', 'color': '#10b981'},
            {'name': 'Salário', 'color': '#22c55e'},
            {'name': 'Saúde', 'color': '#ef4444'},
            {'name': 'Investimentos', 'color': '#8b5cf6'},
            {'name': 'Outros', 'color': '#6b7280'},
        ]
        tags_instances = {}
        for tag_dict in tags_data:
            tag = Tag.objects.create(name=tag_dict['name'], color=tag_dict['color'])
            tags_instances[tag_dict['name']] = tag
            
        self.stdout.write(self.style.SUCCESS(f'{len(tags_instances)} Tags criadas.'))
        
        # 4. Criar Cartões de Crédito
        nubank = CreditCard.objects.create(
            name='Nubank',
            last_digits='9012',
            brand=CreditCard.Brand.MASTERCARD,
            color='#820ad1',
            due_day=10,
            closing_day=3
        )
        itau = CreditCard.objects.create(
            name='Itaú Click',
            last_digits='4321',
            brand=CreditCard.Brand.VISA,
            color='#ff7a00',
            due_day=20,
            closing_day=13
        )
        inter = CreditCard.objects.create(
            name='Inter',
            last_digits='5678',
            brand=CreditCard.Brand.MASTERCARD,
            color='#f27200',
            due_day=5,
            closing_day=28
        )
        self.stdout.write(self.style.SUCCESS('3 Cartões de Crédito criados.'))
        
        # 5. Criar Metas (Goals)
        Goal.objects.create(
            name='Reserva de Emergência',
            target_amount=decimal.Decimal('10000.00'),
            current_amount=decimal.Decimal('6000.00'),
            deadline=today + timedelta(days=120),
            color='#22c55e'
        )
        Goal.objects.create(
            name='Viagem de Férias',
            target_amount=decimal.Decimal('5000.00'),
            current_amount=decimal.Decimal('1500.00'),
            deadline=today + timedelta(days=180),
            color='#3b82f6'
        )
        Goal.objects.create(
            name='Novo Notebook',
            target_amount=decimal.Decimal('7000.00'),
            current_amount=decimal.Decimal('3500.00'),
            deadline=today + timedelta(days=90),
            color='#ec4899'
        )
        self.stdout.write(self.style.SUCCESS('3 Metas Financeiras criadas.'))
        
        # 6. Criar Regras Recorrentes (MONTHLY)
        # Salário Principal: receita mensal recorrente de 6500.00
        salario_rule = RecurringRule.objects.create(
            description='Salário Principal',
            amount=decimal.Decimal('6500.00'),
            type=RecurringRule.TransactionType.INCOME,
            recurrence_type=RecurringRule.RecurrenceType.MONTHLY,
            start_date=today - timedelta(days=25),
            is_active=True
        )
        salario_rule.tags.add(tags_instances['Salário'])
        
        # Aluguel: despesa mensal recorrente de 1800.00
        aluguel_rule = RecurringRule.objects.create(
            description='Aluguel da Casa',
            amount=decimal.Decimal('1800.00'),
            type=RecurringRule.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.MONTHLY,
            start_date=today - timedelta(days=20),
            is_active=True
        )
        aluguel_rule.tags.add(tags_instances['Moradia'])
        
        # Netflix: despesa mensal recorrente de 55.90
        netflix_rule = RecurringRule.objects.create(
            description='Assinatura Netflix',
            amount=decimal.Decimal('55.90'),
            type=RecurringRule.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.MONTHLY,
            start_date=today - timedelta(days=30),
            is_active=True
        )
        netflix_rule.tags.add(tags_instances['Lazer'])
        
        # Spotify: despesa mensal recorrente de 34.90
        spotify_rule = RecurringRule.objects.create(
            description='Spotify Family',
            amount=decimal.Decimal('34.90'),
            type=RecurringRule.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.MONTHLY,
            start_date=today - timedelta(days=40),
            is_active=True
        )
        spotify_rule.tags.add(tags_instances['Lazer'])
        
        # Como o project_cash_flow e list de transações já chamam a materialização sob demanda,
        # opcionalmente chamamos aqui para gerar as transações iniciais das regras MONTHLY
        salario_rule.materialize_monthly_transactions(months_ahead=6)
        aluguel_rule.materialize_monthly_transactions(months_ahead=6)
        netflix_rule.materialize_monthly_transactions(months_ahead=6)
        spotify_rule.materialize_monthly_transactions(months_ahead=6)
        
        self.stdout.write(self.style.SUCCESS('Regras Recorrentes Mensais criadas e materializadas.'))
        
        # 7. Criar Regras Recorrentes Parceladas (INSTALLMENT)
        # Compra de Sofá: 10 parcelas de 120.00 no Nubank, valor total 1200.00
        sofa_rule = RecurringRule.objects.create(
            description='Compra de Sofá',
            amount=decimal.Decimal('1200.00'),
            type=RecurringRule.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.INSTALLMENT,
            total_installments=10,
            start_date=today - timedelta(days=60),
            credit_card=nubank,
            is_active=True
        )
        sofa_rule.amount = (sofa_rule.amount / decimal.Decimal('10')).quantize(decimal.Decimal('0.01'))
        sofa_rule.save()
        sofa_rule.tags.add(tags_instances['Moradia'])
        sofa_rule.generate_installment_transactions()
        
        # Curso de Inglês: 6 parcelas de 250.00 no Itaú, valor total 1500.00
        ingles_rule = RecurringRule.objects.create(
            description='Curso de Inglês',
            amount=decimal.Decimal('1500.00'),
            type=RecurringRule.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.INSTALLMENT,
            total_installments=6,
            start_date=today - timedelta(days=30),
            credit_card=itau,
            is_active=True
        )
        ingles_rule.amount = (ingles_rule.amount / decimal.Decimal('6')).quantize(decimal.Decimal('0.01'))
        ingles_rule.save()
        ingles_rule.tags.add(tags_instances['Outros'])
        ingles_rule.generate_installment_transactions()
        
        self.stdout.write(self.style.SUCCESS('Regras Parceladas criadas e parcelas geradas.'))
        
        # 8. Criar Lançamentos Avulsos (Transactions)
        # Antes da data de referência (Atenuação Histórica)
        # Supermercado há 18 dias (referência é há 15 dias)
        supermercado = Transaction.objects.create(
            description='Supermercado Semanal',
            amount=decimal.Decimal('350.00'),
            due_date=today - timedelta(days=18),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PAID
        )
        supermercado.tags.add(tags_instances['Alimentação'])
        
        # Pós data de referência, antes de hoje
        jantar = Transaction.objects.create(
            description='Jantar de Fim de Semana',
            amount=decimal.Decimal('120.00'),
            due_date=today - timedelta(days=10),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PAID
        )
        jantar.tags.add(tags_instances['Lazer'])
        
        posto = Transaction.objects.create(
            description='Posto de Gasolina',
            amount=decimal.Decimal('150.00'),
            due_date=today - timedelta(days=5),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PAID
        )
        posto.tags.add(tags_instances['Transporte'])
        
        freelance = Transaction.objects.create(
            description='Freelance Desenvolvimento',
            amount=decimal.Decimal('1200.00'),
            due_date=today - timedelta(days=2),
            type=Transaction.TransactionType.INCOME,
            status=Transaction.Status.PAID
        )
        freelance.tags.add(tags_instances['Salário'])
        
        # Lançamentos Futuros Pendentes
        farmacia = Transaction.objects.create(
            description='Compra na Farmácia',
            amount=decimal.Decimal('85.00'),
            due_date=today + timedelta(days=3),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PENDING
        )
        farmacia.tags.add(tags_instances['Saúde'])
        
        uber = Transaction.objects.create(
            description='Corrida de Uber',
            amount=decimal.Decimal('35.00'),
            due_date=today + timedelta(days=1),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PENDING
        )
        uber.tags.add(tags_instances['Transporte'])
        
        academia = Transaction.objects.create(
            description='Academia Mensal',
            amount=decimal.Decimal('110.00'),
            due_date=today + timedelta(days=5),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PENDING
        )
        academia.tags.add(tags_instances['Saúde'])
        
        cdb = Transaction.objects.create(
            description='Aporte CDB Liquidez',
            amount=decimal.Decimal('500.00'),
            due_date=today + timedelta(days=15),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PENDING
        )
        cdb.tags.add(tags_instances['Investimentos'])
        
        monitor = Transaction.objects.create(
            description='Venda de Monitor Antigo',
            amount=decimal.Decimal('300.00'),
            due_date=today + timedelta(days=12),
            type=Transaction.TransactionType.INCOME,
            status=Transaction.Status.PENDING
        )
        monitor.tags.add(tags_instances['Outros'])
        
        self.stdout.write(self.style.SUCCESS('Transações avulsas criadas.'))
        self.stdout.write(self.style.SUCCESS('Sementeira concluída! O banco de dados está pronto para testes de usabilidade.'))
